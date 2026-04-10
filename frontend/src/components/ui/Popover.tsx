import { createPortal } from "react-dom";
import { useAnchoredPopover } from "@/hooks/useAnchoredPopover";
import { UI_LAYERS } from "@/utils/ui-layers";
import type { RefObject, ReactNode, CSSProperties } from "react";

// ---------------------------------------------------------------------------
// Popover - shared popover primitive
// ---------------------------------------------------------------------------
// All popovers should use this component instead of manually wiring
// createPortal + useAnchoredPopover. Rendering through a portal lets the panel
// escape parent stacking contexts (such as header backdrop blur), keeps the
// background opaque, and centralizes z-index management.

/** Default panel background color (gray-900 = rgb(17 24 39)). */
export const POPOVER_BG = "rgb(17 24 39)";

type PopoverAlign = "start" | "center" | "end";
type PopoverLayer = keyof typeof UI_LAYERS;

interface PopoverProps {
  open: boolean;
  onClose?: () => void;
  anchorRef: RefObject<HTMLElement | null>;
  children: ReactNode;
  /** Tailwind width class, e.g. "w-72", "w-96" */
  width?: string;
  /** Extra className appended to the panel root. */
  className?: string;
  /** Extra inline styles. */
  style?: CSSProperties;
  /** Anchor offset in px. Defaults to 8. */
  sideOffset?: number;
  /** Alignment mode. Defaults to "end". */
  align?: PopoverAlign;
  /** z-index layer. Defaults to "workspacePopover". */
  layer?: PopoverLayer;
  /** Custom background color. Defaults to POPOVER_BG. */
  backgroundColor?: string;
}

export function Popover({
  open,
  onClose,
  anchorRef,
  children,
  width = "w-72",
  className = "",
  style,
  sideOffset = 8,
  align,
  layer = "workspacePopover",
  backgroundColor = POPOVER_BG,
}: PopoverProps) {
  const { panelRef, positionStyle } = useAnchoredPopover({
    open,
    anchorRef,
    onClose,
    sideOffset,
    align,
  });

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div
      ref={panelRef}
      className={`fixed isolate ${width} ${UI_LAYERS[layer]} ${className}`}
      style={{
        ...positionStyle,
        backgroundColor,
        ...style,
      }}
    >
      {children}
    </div>,
    document.body,
  );
}
