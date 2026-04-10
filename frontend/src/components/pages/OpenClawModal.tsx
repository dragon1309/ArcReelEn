/**
 * OpenClaw integration guide modal.
 * Includes a copyable prompt, dynamic skill.md URL, a three-step guide, and
 * a shortcut to the API key settings page.
 */
import { useCallback, useMemo, useState } from "react";
import { copyText } from "@/utils/clipboard";
import { Check, Copy, ExternalLink, X } from "lucide-react";
import { useLocation } from "wouter";

// 🦞 SVG lobster icon (inline, no external dep)
function LobsterIcon({ className }: { className?: string }) {
  return (
    <span className={className} aria-hidden="true" role="img">
      🦞
    </span>
  );
}

interface OpenClawModalProps {
  onClose: () => void;
}

// Static step data kept outside the component to avoid recreating it on render.
const STEPS = [
  {
    step: "01",
    title: "Send the prompt above to OpenClaw",
    desc: "Copy the prompt and paste it into OpenClaw",
  },
  {
    step: "02",
    title: "Let OpenClaw read the skill document",
    desc: "OpenClaw will read the ArcReel skill document and learn the available tools and API flows",
  },
  {
    step: "03",
    title: "Create videos through ArcReel",
    desc: "Describe your creative goal and OpenClaw will use ArcReel for project work, script generation, and video creation",
  },
] as const;

export function OpenClawModal({ onClose }: OpenClawModalProps) {
  const [, navigate] = useLocation();
  const [copied, setCopied] = useState(false);

  // Build the skill URL from the current host.
  const skillUrl = useMemo(
    () => `${window.location.origin}/skill.md`,
    [],
  );

  const systemPrompt = useMemo(
    () => `Read ${skillUrl} and follow the skill to learn how to create videos with ArcReel`,
    [skillUrl],
  );

  const handleCopyPrompt = useCallback(async () => {
    await copyText(systemPrompt);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [systemPrompt]);

  // Jump directly to API key management.
  const handleGoToApiKeys = useCallback(() => {
    onClose();
    navigate("/app/settings?section=api-keys");
  }, [navigate, onClose]);

  const handleBackdropClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (e.target === e.currentTarget) onClose();
    },
    [onClose],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose],
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4 py-8"
      onClick={handleBackdropClick}
      onKeyDown={handleKeyDown}
    >
      <div className="relative flex w-full max-w-lg flex-col rounded-2xl border border-gray-800 bg-gray-900 shadow-2xl shadow-black/60 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-gray-800 bg-gray-900 px-5 py-4">
          <div className="flex items-center gap-2.5">
            <LobsterIcon className="text-xl leading-none" />
            <div>
              <h2 className="text-sm font-semibold text-gray-100">OpenClaw Integration Guide</h2>
              <p className="text-xs text-gray-500">Connect ArcReel to your OpenClaw AI agent</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-gray-500 transition-colors hover:bg-gray-800 hover:text-gray-300"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-5 space-y-5">
          {/* Prompt section */}
          <div>
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs font-medium text-gray-400">Prompt</span>
              <button
                type="button"
                onClick={() => void handleCopyPrompt()}
                className="inline-flex items-center gap-1 rounded-md border border-gray-700 bg-gray-800 px-2 py-1 text-xs text-gray-300 transition-colors hover:border-gray-600 hover:bg-gray-700"
              >
                {copied ? (
                  <>
                    <Check className="h-3 w-3 text-emerald-400" />
                    Copied
                  </>
                ) : (
                  <>
                    <Copy className="h-3 w-3" />
                    Copy
                  </>
                )}
              </button>
            </div>
            <div className="rounded-xl border border-indigo-500/20 bg-gray-950 p-3">
              <pre className="whitespace-pre-wrap font-mono text-xs leading-5 text-indigo-200">
                {systemPrompt}
              </pre>
            </div>
            <p className="mt-1.5 text-xs text-gray-600">
              Skill document:
              <a
                href={skillUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="ml-1 inline-flex items-center gap-0.5 text-indigo-400 hover:text-indigo-300"
              >
                {skillUrl}
                <ExternalLink className="h-3 w-3" />
              </a>
            </p>
          </div>

          {/* Three-step guide */}
          <div>
            <div className="mb-3 text-xs font-medium text-gray-400">How to use it</div>
            <div className="space-y-2">
              {STEPS.map(({ step, title, desc }) => (
                <div
                  key={step}
                  className="flex gap-3 rounded-xl border border-gray-800 bg-gray-950/50 px-3.5 py-3"
                >
                  <div className="flex-shrink-0 font-mono text-xs font-bold text-indigo-500/70 pt-0.5">
                    {step}
                  </div>
                  <div>
                    <div className="text-xs font-semibold text-gray-200">{title}</div>
                    <div className="mt-0.5 text-xs leading-4.5 text-gray-500">{desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Actions */}
          <div className="flex gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 rounded-xl border border-gray-700 bg-gray-800 px-4 py-2.5 text-sm text-gray-300 transition-colors hover:border-gray-600 hover:bg-gray-700"
            >
              Close
            </button>
            <button
              type="button"
              onClick={handleGoToApiKeys}
              className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-indigo-500"
            >
              Get API Token
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
