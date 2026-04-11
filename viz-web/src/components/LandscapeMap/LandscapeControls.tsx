interface LandscapeControlsProps {
  scale: number;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onReset: () => void;
}

export function LandscapeControls({ scale, onZoomIn, onZoomOut, onReset }: LandscapeControlsProps) {
  return (
    <>
      <div className="absolute top-2 right-2 z-10 flex flex-col bg-card border border-ink rounded-sm overflow-hidden">
        <button
          type="button"
          aria-label="Zoom in"
          onClick={onZoomIn}
          className="w-6 h-6 p-0 bg-transparent text-ink font-mono text-[0.78rem] cursor-pointer hover:bg-ink hover:text-paper border-0 border-b border-ink"
        >
          +
        </button>
        <button
          type="button"
          aria-label="Zoom out"
          onClick={onZoomOut}
          className="w-6 h-6 p-0 bg-transparent text-ink font-mono text-[0.78rem] cursor-pointer hover:bg-ink hover:text-paper border-0 border-b border-ink"
        >
          −
        </button>
        <button
          type="button"
          aria-label="Reset view"
          onClick={onReset}
          className="w-6 h-6 p-0 bg-transparent text-ink font-mono text-[0.72rem] cursor-pointer hover:bg-ink hover:text-paper border-0"
        >
          ⌂
        </button>
      </div>
      <div className="absolute bottom-2 left-2 z-10 font-mono text-[0.6rem] text-muted bg-card border border-ink/20 rounded-sm px-1.5 py-0.5">
        × {scale.toFixed(2)}
      </div>
      <div className="absolute bottom-2 right-2 z-10 font-mono text-[0.56rem] text-muted bg-card border border-ink/20 rounded-sm px-1.5 py-0.5">
        + − 0 ← → ↑ ↓
      </div>
    </>
  );
}
