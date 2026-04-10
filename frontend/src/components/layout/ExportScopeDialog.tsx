import { useState, useEffect } from "react";
import { Package, History, Clapperboard, ArrowLeft, Loader2 } from "lucide-react";
import { Popover } from "@/components/ui/Popover";
import type { RefObject } from "react";
import type { EpisodeMeta } from "@/types/project";

export type ExportScope = "current" | "full" | "jianying-draft";

const DRAFT_PATH_STORAGE_KEY = "arcreel_jianying_draft_path";

function getDefaultDraftPath(): string {
  const isWindows =
    typeof navigator !== "undefined" &&
    navigator.userAgent.includes("Windows");
  return isWindows
    ? String.raw`C:\Users\<your-username>\AppData\Local\JianyingPro\User Data\Projects\com.lveditor.draft`
    : "/Users/<your-username>/Movies/JianyingPro/User Data/Projects/com.lveditor.draft";
}

interface ExportScopeDialogProps {
  open: boolean;
  onClose: () => void;
  onSelect: (scope: ExportScope) => void;
  anchorRef: RefObject<HTMLElement | null>;
  episodes?: EpisodeMeta[];
  onJianyingExport?: (episode: number, draftPath: string, jianyingVersion: string) => void;
  jianyingExporting?: boolean;
}

export function ExportScopeDialog({
  open,
  onClose,
  onSelect,
  anchorRef,
  episodes = [],
  onJianyingExport,
  jianyingExporting = false,
}: ExportScopeDialogProps) {
  const [mode, setMode] = useState<"select" | "jianying-form">("select");
  const [selectedEpisode, setSelectedEpisode] = useState<number>(
    episodes.length > 0 ? episodes[0].episode : 1,
  );
  const [draftPath, setDraftPath] = useState<string>(
    () => localStorage.getItem(DRAFT_PATH_STORAGE_KEY) || getDefaultDraftPath(),
  );
  const [jianyingVersion, setJianyingVersion] = useState("6");

  // Reset mode when the popover closes.
  useEffect(() => {
    if (!open) {
      setMode("select");
    }
  }, [open]);

  // Sync the selected episode whenever the episode list changes.
  useEffect(() => {
    if (episodes.length > 0) {
      setSelectedEpisode(episodes[0].episode);
    }
  }, [episodes]);

  const handleJianyingSubmit = () => {
    if (!draftPath.trim() || !onJianyingExport) return;
    localStorage.setItem(DRAFT_PATH_STORAGE_KEY, draftPath.trim());
    onJianyingExport(selectedEpisode, draftPath.trim(), jianyingVersion);
  };

  return (
    <Popover
      open={open}
      onClose={onClose}
      anchorRef={anchorRef}
      width="w-80"
      className="rounded-lg border border-gray-700 p-3 shadow-xl"
    >
      {mode === "select" ? (
        <>
          <p className="mb-3 text-xs font-medium text-gray-300">Choose export scope</p>
          <div className="flex flex-col gap-2">
            <button
              type="button"
              onClick={() => onSelect("current")}
              className="flex items-start gap-3 rounded-md border border-gray-700 px-3 py-2.5 text-left transition-colors hover:border-indigo-500 hover:bg-indigo-500/10"
            >
              <Package className="mt-0.5 h-4 w-4 shrink-0 text-indigo-400" />
              <div>
                <div className="text-sm font-medium text-gray-200">
                  Current version only
                  <span className="ml-1.5 rounded bg-indigo-500/20 px-1.5 py-0.5 text-[10px] text-indigo-300">
                    Recommended
                  </span>
                </div>
                <p className="mt-0.5 text-xs text-gray-500">
                  Excludes version history for a smaller archive
                </p>
              </div>
            </button>
            <button
              type="button"
              onClick={() => onSelect("full")}
              className="flex items-start gap-3 rounded-md border border-gray-700 px-3 py-2.5 text-left transition-colors hover:border-gray-500 hover:bg-gray-800"
            >
              <History className="mt-0.5 h-4 w-4 shrink-0 text-gray-400" />
              <div>
                <div className="text-sm font-medium text-gray-200">All data</div>
                <p className="mt-0.5 text-xs text-gray-500">
                  Includes full version history
                </p>
              </div>
            </button>
            <button
              type="button"
              onClick={() => setMode("jianying-form")}
              className="flex items-start gap-3 rounded-md border border-gray-700 px-3 py-2.5 text-left transition-colors hover:border-amber-500 hover:bg-amber-500/10"
            >
              <Clapperboard className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
              <div>
                <div className="text-sm font-medium text-gray-200">
                  Export as Jianying draft
                </div>
                <p className="mt-0.5 text-xs text-gray-500">
                  Create a Jianying-importable draft ZIP
                </p>
              </div>
            </button>
          </div>
        </>
      ) : (
        <>
          <div className="mb-3 flex items-center gap-2">
            <button
              type="button"
              onClick={() => setMode("select")}
              className="rounded p-0.5 text-gray-400 transition-colors hover:bg-gray-800 hover:text-gray-200"
              aria-label="Back"
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
            <p className="text-xs font-medium text-gray-300">Export as Jianying draft</p>
          </div>
          <div className="flex flex-col gap-3">
            {/* Episode selector - hidden when only one episode */}
            {episodes.length > 1 && (
              <div>
                <label htmlFor="jianying-episode-select" className="mb-1 block text-xs text-gray-400">
                  Episode
                </label>
                <select
                  id="jianying-episode-select"
                  value={selectedEpisode}
                  onChange={(e) => setSelectedEpisode(Number(e.target.value))}
                  className="w-full rounded-md border border-gray-700 bg-gray-800 px-2.5 py-1.5 text-sm text-gray-200 outline-none focus:border-indigo-500"
                >
                  {episodes.map((ep) => (
                    <option key={ep.episode} value={ep.episode}>
                      Episode {ep.episode} - {ep.title}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Jianying version selector */}
            <div>
              <label htmlFor="jianying-version-select" className="mb-1 block text-xs text-gray-400">
                Jianying version
              </label>
              <select
                id="jianying-version-select"
                value={jianyingVersion}
                onChange={(e) => setJianyingVersion(e.target.value)}
                className="w-full rounded-md border border-gray-700 bg-gray-800 px-2.5 py-1.5 text-sm text-gray-200 outline-none focus:border-indigo-500"
              >
                <option value="6">Jianying 6.0 and later (recommended)</option>
                <option value="5">Jianying 5.x</option>
              </select>
            </div>

            {/* Draft path input */}
            <div>
              <label htmlFor="jianying-draft-path" className="mb-1 block text-xs text-gray-400">
                Draft directory path
              </label>
              <input
                id="jianying-draft-path"
                type="text"
                value={draftPath}
                onChange={(e) => setDraftPath(e.target.value)}
                placeholder="Jianying draft directory path"
                className="w-full rounded-md border border-gray-700 bg-gray-800 px-2.5 py-1.5 text-sm text-gray-200 placeholder:text-gray-600 outline-none focus:border-indigo-500"
              />
              <p className="mt-1.5 text-[11px] leading-relaxed text-gray-500">
                Enter the full Jianying draft directory path. In Jianying, open Settings and check Draft location.
              </p>
            </div>

            {/* Submit */}
            <button
              type="button"
              onClick={handleJianyingSubmit}
              disabled={!draftPath.trim() || jianyingExporting}
              className="flex items-center justify-center gap-1.5 rounded-md bg-amber-600 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-amber-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {jianyingExporting ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Exporting...
                </>
              ) : (
                "Export draft"
              )}
            </button>
          </div>
        </>
      )}
    </Popover>
  );
}
