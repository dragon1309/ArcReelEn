import { useCallback, useEffect, useRef } from "react";
import { API } from "@/api";
import { uid } from "@/utils/id";
import { useAssistantStore } from "@/stores/assistant-store";
import type {
  AssistantSnapshot,
  PendingQuestion,
  SessionMeta,
  SessionStatus,
  Turn,
} from "@/types";

export interface AttachedImage {
  id: string;
  dataUrl: string;
  mimeType: string;
}

// ---------------------------------------------------------------------------
// Helpers - migrated from the old use-assistant-state.js.
// ---------------------------------------------------------------------------

function parseSsePayload(event: MessageEvent): Record<string, unknown> {
  try {
    return JSON.parse(event.data || "{}");
  } catch {
    return {};
  }
}

function applyTurnPatch(prev: Turn[], patch: Record<string, unknown>): Turn[] {
  const op = patch.op as string;
  if (op === "reset") return (patch.turns as Turn[]) ?? [];
  if (op === "append" && patch.turn) {
    const newTurn = patch.turn as Turn;
    // Remove the trailing optimistic turn once the backend appends the real user turn.
    if (
      newTurn.type === "user" &&
      prev.length > 0 &&
      prev.at(-1)?.uuid?.startsWith(OPTIMISTIC_PREFIX)
    ) {
      return [...prev.slice(0, -1), newTurn];
    }
    return [...prev, newTurn];
  }
  if (op === "replace_last" && patch.turn) {
    return prev.length === 0
      ? [patch.turn as Turn]
      : [...prev.slice(0, -1), patch.turn as Turn];
  }
  return prev;
}

const TERMINAL = new Set(["completed", "error", "interrupted"]);
const OPTIMISTIC_PREFIX = "optimistic-";

function extractTurnText(turn: Turn): string {
  return (
    turn.content
      ?.filter((b) => b.type === "text")
      .map((b) => b.text ?? "")
      .join("") ?? ""
  );
}

function parseTurnTimestamp(turn: Turn | null): number | null {
  if (!turn?.timestamp) return null;
  const parsed = Date.parse(turn.timestamp);
  return Number.isNaN(parsed) ? null : parsed;
}

function findLatestUserTurn(turns: Turn[]): Turn | null {
  for (let i = turns.length - 1; i >= 0; i--) {
    if (turns[i].type === "user") return turns[i];
  }
  return null;
}

// ---------------------------------------------------------------------------
// localStorage helpers - remember the last session used for each project.
// ---------------------------------------------------------------------------

const LAST_SESSION_KEY = "arcreel:lastSessionByProject";

function getLastSessionId(projectName: string): string | null {
  try {
    const map = JSON.parse(localStorage.getItem(LAST_SESSION_KEY) || "{}");
    return map[projectName] ?? null;
  } catch {
    return null;
  }
}

function saveLastSessionId(projectName: string, sessionId: string): void {
  try {
    const map = JSON.parse(localStorage.getItem(LAST_SESSION_KEY) || "{}");
    map[projectName] = sessionId;
    localStorage.setItem(LAST_SESSION_KEY, JSON.stringify(map));
  } catch {
    // Fail silently.
  }
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * Manage the AI assistant session lifecycle:
 * - load/create sessions
 * - send messages
 * - receive SSE updates
 * - interrupt sessions
 */
export function useAssistantSession(projectName: string | null) {
  const store = useAssistantStore;
  const streamRef = useRef<EventSource | null>(null);
  const streamSessionRef = useRef<string | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const statusRef = useRef<string>("idle");
  const pendingSendVersionRef = useRef(0);

  const syncPendingQuestion = useCallback((question: PendingQuestion | null) => {
    store.getState().setPendingQuestion(question);
    store.getState().setAnsweringQuestion(false);
  }, [store]);

  const clearPendingQuestion = useCallback(() => {
    syncPendingQuestion(null);
  }, [syncPendingQuestion]);

  const invalidatePendingSend = useCallback(() => {
    pendingSendVersionRef.current += 1;
    store.getState().setSending(false);
  }, [store]);

  const restoreFailedSend = useCallback((
    sessionId: string,
    optimisticUuid: string,
    previousStatus: SessionStatus | null,
  ) => {
    if (store.getState().currentSessionId !== sessionId) return;

    store.getState().setTurns(
      store.getState().turns.filter((turn) => turn.uuid !== optimisticUuid),
    );
    statusRef.current = previousStatus ?? "idle";
    store.getState().setSessionStatus(previousStatus ?? "idle");
    store.getState().setSending(false);
  }, [store]);

  const applySnapshot = useCallback((snapshot: Partial<AssistantSnapshot>) => {
    const snapshotTurns = (snapshot.turns as Turn[]) ?? [];
    const currentTurns = store.getState().turns;

    // Preserve the trailing optimistic turn only when the snapshot does not yet contain
    // the current user turn. Match on content instead of UUID because optimistic UUIDs
    // never match the backend-issued UUIDs.
    const lastTurn = currentTurns.at(-1);
    let shouldPreserveOptimistic = false;

    if (lastTurn?.uuid?.startsWith(OPTIMISTIC_PREFIX)) {
      const optText = extractTurnText(lastTurn);

      if (optText) {
        const latestUserTurn = findLatestUserTurn(snapshotTurns);
        if (!latestUserTurn || extractTurnText(latestUserTurn) !== optText) {
          shouldPreserveOptimistic = true;
        } else {
          const latestUserTs = parseTurnTimestamp(latestUserTurn);
          const optimisticTs = parseTurnTimestamp(lastTurn);
          shouldPreserveOptimistic = Boolean(
            latestUserTs !== null &&
            optimisticTs !== null &&
            latestUserTs < optimisticTs,
          );
        }
      }
    }

    if (shouldPreserveOptimistic && lastTurn) {
      store.getState().setTurns([...snapshotTurns, lastTurn]);
    } else {
      store.getState().setTurns(snapshotTurns);
    }

    store.getState().setDraftTurn((snapshot.draft_turn as Turn) ?? null);
    syncPendingQuestion(getPendingQuestionFromSnapshot(snapshot));
  }, [store, syncPendingQuestion]);

  // Close the stream.
  const closeStream = useCallback(() => {
    if (reconnectRef.current) {
      clearTimeout(reconnectRef.current);
      reconnectRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.close();
      streamRef.current = null;
    }
    streamSessionRef.current = null;
  }, []);

  // Connect the SSE stream.
  const connectStream = useCallback(
    (sessionId: string) => {
      // Skip reconnecting when the current stream already targets this session and is healthy.
      if (
        streamRef.current &&
        streamSessionRef.current === sessionId &&
        streamRef.current.readyState !== EventSource.CLOSED
      ) {
        return;
      }

      closeStream();
      streamSessionRef.current = sessionId;

      const url = API.getAssistantStreamUrl(projectName!, sessionId);
      const source = new EventSource(url);
      streamRef.current = source;
      const isActiveStream = () =>
        streamRef.current === source &&
        streamSessionRef.current === sessionId &&
        store.getState().currentSessionId === sessionId;

      source.addEventListener("snapshot", (event) => {
        if (!isActiveStream()) return;
        const data = parseSsePayload(event as MessageEvent);
        const isSending = store.getState().sending;

        // While sending, the backend may not have switched the session to "running" yet.
        // In that case the SSE connection can briefly attach to the old "completed" session,
        // receive a stale snapshot/status, and disconnect immediately. Ignore that stale data
        // so the optimistic frontend state stays intact.
        if (isSending && typeof data.status === "string" && data.status !== "running") {
          return;
        }

        applySnapshot(data as Partial<AssistantSnapshot>);

        if (typeof data.status === "string") {
          store.getState().setSessionStatus(data.status as "idle");
          statusRef.current = data.status as string;
          // Clear the sending flag for any valid status; stale states were already filtered.
          // In particular, "running" confirms the backend received the message. If we do not
          // clear sending here, a later "completed" could be filtered by the isSending guard.
          store.getState().setSending(false);
        }
      });

      source.addEventListener("patch", (event) => {
        if (!isActiveStream()) return;
        const payload = parseSsePayload(event as MessageEvent);
        const patch = (payload.patch ?? payload) as Record<string, unknown>;
        store.getState().setTurns(applyTurnPatch(store.getState().turns, patch));
        if ("draft_turn" in payload) {
          store.getState().setDraftTurn((payload.draft_turn as Turn) ?? null);
        }
      });

      source.addEventListener("delta", (event) => {
        if (!isActiveStream()) return;
        const payload = parseSsePayload(event as MessageEvent);
        if ("draft_turn" in payload) {
          store.getState().setDraftTurn((payload.draft_turn as Turn) ?? null);
        }
      });

      source.addEventListener("status", (event) => {
        if (!isActiveStream()) return;
        const data = parseSsePayload(event as MessageEvent);
        const status = (data.status as string) ?? statusRef.current;
        const isSending = store.getState().sending;

        // While sending, ignore terminal statuses from the old session. For non-running sessions
        // the backend emits status:"completed" and closes the SSE connection. That stale status
        // should not trigger closeStream/setSending(false). The onerror handler will reconnect once
        // the backend session has moved to "running".
        if (isSending && TERMINAL.has(status) && status !== "error") {
          return;
        }

        statusRef.current = status;
        store.getState().setSessionStatus(status as "idle");

        if (TERMINAL.has(status)) {
          store.getState().setSending(false);
          store.getState().setInterrupting(false);
          clearPendingQuestion();
          if (status !== "interrupted") {
            store.getState().setDraftTurn(null);
          }
          closeStream();

          // Refresh the session list after the turn completes so the SDK summary title is picked up.
          if (projectName) {
            API.listAssistantSessions(projectName).then((res) => {
              const fresh = res.sessions ?? [];
              if (fresh.length > 0) store.getState().setSessions(fresh);
            }).catch(() => {/* Fail silently. */});
          }
        }
      });

      source.addEventListener("question", (event) => {
        if (!isActiveStream()) return;
        const payload = parseSsePayload(event as MessageEvent);
        const pendingQuestion = getPendingQuestionFromEvent(payload);
        if (pendingQuestion) {
          syncPendingQuestion(pendingQuestion);
        }
      });

      source.onerror = () => {
        if (!isActiveStream()) return;
        // Reconnect if the session is running or the frontend is currently sending a message.
        // The latter handles the case where the backend immediately closes the SSE stream for the
        // old "completed" session; by the time we reconnect, the backend session is "running".
        if (statusRef.current === "running" || store.getState().sending) {
          reconnectRef.current = setTimeout(() => {
            connectStream(sessionId);
          }, 3000);
        }
      };
    },
    [applySnapshot, clearPendingQuestion, projectName, closeStream, store, syncPendingQuestion],
  );

  // Load sessions.
  useEffect(() => {
    if (!projectName) return;
    let cancelled = false;

    async function init() {
      store.getState().setMessagesLoading(true);
      try {
        // Fetch the session list.
        const res = await API.listAssistantSessions(projectName!);
        const sessions = res.sessions ?? [];
        store.getState().setSessions(sessions);

        // Prefer the last selected session if it still exists.
        const lastId = getLastSessionId(projectName!);
        const sessionId = (lastId && sessions.some((s: SessionMeta) => s.id === lastId))
          ? lastId
          : sessions[0]?.id;
        if (!sessionId) {
          store.getState().setCurrentSessionId(null);
          clearPendingQuestion();
          store.getState().setMessagesLoading(false);
          return;
        }
        if (cancelled) return;

        store.getState().setCurrentSessionId(sessionId);

        // Load the session snapshot.
        const session = await API.getAssistantSession(projectName!, sessionId);
        const raw = session as Record<string, unknown>;
        const sessionObj = (raw.session ?? raw) as Record<string, unknown>;
        const status = (sessionObj.status as string) ?? "idle";
        statusRef.current = status;
        store.getState().setSessionStatus(status as "idle");

        if (status === "running") {
          connectStream(sessionId);
        } else {
          const snapshot = await API.getAssistantSnapshot(projectName!, sessionId);
          if (cancelled) return;
          applySnapshot(snapshot);
        }
      } catch {
        // Fail silently.
      } finally {
        if (!cancelled) store.getState().setMessagesLoading(false);
      }
    }

    // Load the skill list.
    API.listAssistantSkills(projectName)
      .then((res) => {
        if (!cancelled) store.getState().setSkills(res.skills ?? []);
      })
      .catch(() => {});

    init();

    return () => {
      cancelled = true;
      invalidatePendingSend();
      closeStream();
    };
  }, [
    projectName,
    applySnapshot,
    clearPendingQuestion,
    connectStream,
    closeStream,
    invalidatePendingSend,
    store,
  ]);

  // Send a message.
  const sendMessage = useCallback(
    async (content: string, images?: AttachedImage[]) => {
      if ((!content.trim() && (!images || images.length === 0)) || store.getState().sending) return;

      const sendVersion = pendingSendVersionRef.current + 1;
      pendingSendVersionRef.current = sendVersion;
      const previousStatus = store.getState().sessionStatus;
      let sessionId = store.getState().currentSessionId;
      let optimisticUuid = "";
      store.getState().setSending(true);
      store.getState().setError(null);

      try {
        // Extract base64 payloads.
        const imagePayload = images?.map((img) => ({
          data: img.dataUrl.split(",")[1] ?? "",
          media_type: img.mimeType,
        }));

        // Optimistic update: show the user message in the UI immediately.
        const optimisticContent: import("@/types").ContentBlock[] = [
          ...(imagePayload ?? []).map((img) => ({
            type: "image" as const,
            source: {
              type: "base64" as const,
              media_type: img.media_type,
              data: img.data,
            },
          })),
          ...(content.trim() ? [{ type: "text" as const, text: content.trim() }] : []),
        ];
        const optimisticTurn: Turn = {
          type: "user",
          content: optimisticContent,
          uuid: `${OPTIMISTIC_PREFIX}${uid()}`,
          timestamp: new Date().toISOString(),
        };
        optimisticUuid = optimisticTurn.uuid ?? "";
        store.getState().setTurns([...store.getState().turns, optimisticTurn]);
        statusRef.current = "running";
        store.getState().setSessionStatus("running");

        // Send through the unified endpoint for both new and existing sessions.
        const result = await API.sendAssistantMessage(
          projectName!,
          content,
          sessionId,  // null for new session
          imagePayload,
        );

        if (pendingSendVersionRef.current !== sendVersion) return;

        const returnedSessionId = result.session_id;

        // New session: update the store.
        if (!sessionId) {
          const newSession: SessionMeta = {
            id: returnedSessionId,
            project_name: projectName!,
            title: content.trim().slice(0, 30) || "Image Message",
            status: "running",
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          };
          store.getState().setCurrentSessionId(returnedSessionId);
          store.getState().setSessions([newSession, ...store.getState().sessions]);
          store.getState().setIsDraftSession(false);
          saveLastSessionId(projectName!, returnedSessionId);
          sessionId = returnedSessionId;
        }

        if (store.getState().currentSessionId !== sessionId) return;
        connectStream(sessionId);
      } catch (err) {
        if (pendingSendVersionRef.current !== sendVersion) return;
        store.getState().setError((err as Error).message ?? "Failed to send message");
        if (sessionId && optimisticUuid) {
          restoreFailedSend(sessionId, optimisticUuid, previousStatus);
        } else {
          // New-session creation failed: roll back to draft mode.
          store.getState().setTurns(store.getState().turns.filter(t => t.uuid !== optimisticUuid));
          store.getState().setIsDraftSession(true);
          store.getState().setCurrentSessionId(null);
          statusRef.current = previousStatus ?? "idle";
          store.getState().setSessionStatus(previousStatus ?? "idle");
          store.getState().setSending(false);
        }
      }
    },
    [projectName, connectStream, restoreFailedSend, store],
  );

  const answerQuestion = useCallback(
    async (questionId: string, answers: Record<string, string>) => {
      const sessionId = store.getState().currentSessionId;
      if (!projectName || !sessionId) return;

      store.getState().setError(null);
      store.getState().setAnsweringQuestion(true);

      try {
        await API.answerAssistantQuestion(projectName, sessionId, questionId, answers);
        store.getState().setPendingQuestion(null);
      } catch (err) {
        store.getState().setError((err as Error).message ?? "Failed to submit answer");
      } finally {
        store.getState().setAnsweringQuestion(false);
      }
    },
    [projectName, store],
  );

  // Interrupt the session.
  const interrupt = useCallback(async () => {
    const sessionId = store.getState().currentSessionId;
    if (!projectName || !sessionId || statusRef.current !== "running") return;

    store.getState().setInterrupting(true);
    try {
      await API.interruptAssistantSession(projectName, sessionId);
    } catch (err) {
      store.getState().setError((err as Error).message ?? "Failed to interrupt session");
      store.getState().setInterrupting(false);
    }
  }, [projectName, store]);

  // Create a new session lazily: clear state now and defer actual creation until the first send.
  const createNewSession = useCallback(async () => {
    if (!projectName) return;

    invalidatePendingSend();
    closeStream();
    store.getState().setTurns([]);
    store.getState().setDraftTurn(null);
    store.getState().setSessionStatus("idle");
    clearPendingQuestion();
    store.getState().setCurrentSessionId(null);
    store.getState().setIsDraftSession(true);
    statusRef.current = "idle";
  }, [projectName, clearPendingQuestion, closeStream, invalidatePendingSend, store]);

  // Switch to the requested session.
  const switchSession = useCallback(async (sessionId: string) => {
    if (store.getState().currentSessionId === sessionId) return;

    invalidatePendingSend();
    closeStream();
    store.getState().setCurrentSessionId(sessionId);
    store.getState().setIsDraftSession(false);
    store.getState().setTurns([]);
    store.getState().setDraftTurn(null);
    clearPendingQuestion();
    store.getState().setMessagesLoading(true);

    // Remember the selection.
    if (projectName) saveLastSessionId(projectName, sessionId);

    try {
      const res = await API.getAssistantSession(projectName!, sessionId);
      const raw = res as Record<string, unknown>;
      const sessionObj = (raw.session ?? raw) as Record<string, unknown>;
      const status = (sessionObj.status as string) ?? "idle";
      statusRef.current = status;
      store.getState().setSessionStatus(status as "idle");

      if (status === "running") {
        connectStream(sessionId);
      } else {
        const snapshot = await API.getAssistantSnapshot(projectName!, sessionId);
        applySnapshot(snapshot);
      }
    } catch {
      // Fail silently.
    } finally {
      store.getState().setMessagesLoading(false);
    }
  }, [projectName, applySnapshot, clearPendingQuestion, closeStream, connectStream, invalidatePendingSend, store]);

  // Delete the session.
  const deleteSession = useCallback(async (sessionId: string) => {
    if (!projectName) return;
    try {
      await API.deleteAssistantSession(projectName, sessionId);
      const sessions = store.getState().sessions.filter((s) => s.id !== sessionId);
      store.getState().setSessions(sessions);

      // If the deleted session is current, move to the next one.
      if (store.getState().currentSessionId === sessionId) {
        if (sessions.length > 0) {
          await switchSession(sessions[0].id);
        } else {
          invalidatePendingSend();
          closeStream();
          store.getState().setCurrentSessionId(null);
          store.getState().setTurns([]);
          store.getState().setDraftTurn(null);
          store.getState().setSessionStatus(null);
          clearPendingQuestion();
          statusRef.current = "idle";
        }
      }
    } catch {
      // Fail silently.
    }
  }, [projectName, clearPendingQuestion, closeStream, invalidatePendingSend, switchSession, store]);

  return { sendMessage, answerQuestion, interrupt, createNewSession, switchSession, deleteSession };
}

function getPendingQuestionFromSnapshot(
  snapshot: Partial<AssistantSnapshot> | Record<string, unknown>,
): PendingQuestion | null {
  const questions = snapshot.pending_questions as Array<Record<string, unknown>> | undefined;
  const pending = questions?.find(
    (question) =>
      typeof question?.question_id === "string" &&
      Array.isArray(question.questions) &&
      question.questions.length > 0,
  );

  if (!pending) {
    return null;
  }

  return {
    question_id: pending.question_id as string,
    questions: pending.questions as PendingQuestion["questions"],
  };
}

function getPendingQuestionFromEvent(payload: Record<string, unknown>): PendingQuestion | null {
  if (!(typeof payload.question_id === "string" && Array.isArray(payload.questions))) {
    return null;
  }

  return {
    question_id: payload.question_id,
    questions: payload.questions as PendingQuestion["questions"],
  };
}
