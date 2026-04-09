import type { ProjectChange } from "@/types";

const GROUP_NAME_LIMIT = 5;

const ENTITY_LABELS: Record<ProjectChange["entity_type"], string> = {
  project: "projects",
  character: "characters",
  clue: "clues",
  segment: "segments",
  episode: "episodes",
  overview: "project overviews",
  draft: "preprocessing drafts",
};

export interface GroupedProjectChange {
  key: string;
  entityType: ProjectChange["entity_type"];
  action: ProjectChange["action"];
  changes: ProjectChange[];
}

export function buildEntityRevisionKey(
  entityType: ProjectChange["entity_type"],
  entityId: string,
): string {
  return `${entityType}:${entityId}`;
}

export function buildVersionResourceRevisionKey(
  resourceType: "storyboards" | "videos" | "characters" | "clues",
  resourceId: string,
): string {
  if (resourceType === "storyboards" || resourceType === "videos") {
    return buildEntityRevisionKey("segment", resourceId);
  }
  if (resourceType === "characters") {
    return buildEntityRevisionKey("character", resourceId);
  }
  return buildEntityRevisionKey("clue", resourceId);
}

export function groupChangesByType(
  changes: ProjectChange[],
): GroupedProjectChange[] {
  const groups = new Map<string, GroupedProjectChange>();

  for (const change of changes) {
    const key = `${change.entity_type}:${change.action}`;
    const existing = groups.get(key);
    if (existing) {
      existing.changes.push(change);
      continue;
    }
    groups.set(key, {
      key,
      entityType: change.entity_type,
      action: change.action,
      changes: [change],
    });
  }

  return [...groups.values()];
}

function getEntityLabel(group: GroupedProjectChange): string {
  if (group.action === "storyboard_ready") {
    return "storyboards";
  }
  if (group.action === "video_ready") {
    return "videos";
  }
  return ENTITY_LABELS[group.entityType] ?? "items";
}

function getChangeListLabel(change: ProjectChange): string {
  if (
    change.entity_type === "character" ||
    change.entity_type === "clue" ||
    change.entity_type === "segment"
  ) {
    return change.entity_id;
  }
  return change.label;
}

function summarizeGroupNames(group: GroupedProjectChange): string {
  const names = group.changes.slice(0, GROUP_NAME_LIMIT).map(getChangeListLabel);
  const suffix = group.changes.length > GROUP_NAME_LIMIT ? ", and others" : "";
  return `${names.join(", ")}${suffix}`;
}

function formatSingleNotificationText(change: ProjectChange): string {
  if (change.action === "storyboard_ready") {
    return `Generated storyboard for ${change.label}`;
  }
  if (change.action === "video_ready") {
    return `Generated video for ${change.label}`;
  }
  if (change.action === "created") {
    return `Created ${change.label}`;
  }
  if (change.action === "deleted") {
    return `Deleted ${change.label}`;
  }
  return `Updated ${change.label}`;
}

function formatSingleDeferredText(change: ProjectChange): string {
  if (change.action === "storyboard_ready") {
    return `AI generated a storyboard for ${change.label}. Click to open`;
  }
  if (change.action === "video_ready") {
    return `AI generated a video for ${change.label}. Click to open`;
  }
  if (change.action === "created") {
    return `AI created ${change.label}. Click to open`;
  }
  if (change.action === "deleted") {
    return `AI deleted ${change.label}. Click to open`;
  }
  return `AI updated ${change.label}. Click to open`;
}

export function formatGroupedNotificationText(
  group: GroupedProjectChange,
): string {
  if (group.changes.length === 1) {
    return formatSingleNotificationText(group.changes[0]);
  }

  const count = group.changes.length;
  const entityLabel = getEntityLabel(group);
  const summary = summarizeGroupNames(group);

  if (group.action === "storyboard_ready" || group.action === "video_ready") {
    return `Generated ${count} ${entityLabel}: ${summary}`;
  }
  if (group.action === "created") {
    return `Created ${count} ${entityLabel}: ${summary}`;
  }
  if (group.action === "deleted") {
    return `Deleted ${count} ${entityLabel}: ${summary}`;
  }
  return `Updated ${count} ${entityLabel}: ${summary}`;
}

export function formatGroupedDeferredText(
  group: GroupedProjectChange,
): string {
  if (group.changes.length === 1) {
    return formatSingleDeferredText(group.changes[0]);
  }

  const count = group.changes.length;
  const entityLabel = getEntityLabel(group);
  const summary = summarizeGroupNames(group);

  if (group.action === "storyboard_ready" || group.action === "video_ready") {
    return `AI generated ${count} ${entityLabel}: ${summary}. Click to open`;
  }
  if (group.action === "created") {
    return `AI created ${count} ${entityLabel}: ${summary}. Click to open`;
  }
  if (group.action === "deleted") {
    return `AI deleted ${count} ${entityLabel}: ${summary}. Click to open`;
  }
  return `AI updated ${count} ${entityLabel}: ${summary}. Click to open`;
}
