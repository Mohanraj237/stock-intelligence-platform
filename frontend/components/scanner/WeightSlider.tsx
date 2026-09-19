"use client";

interface WeightSliderProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (v: number) => void;
  /** Static helper text, or a function of the current value (e.g. score-band guidance). */
  helperText?: string | ((value: number) => string);
  /** Small trailing note appended after helperText, e.g. "· out of 100". */
  suffix?: string;
}

/**
 * Shared range-slider control used for both the per-scan confluence-score
 * threshold (equity-scanner / live-scanner pages) and the Settings → Scoring
 * category weight sliders — previously duplicated verbatim across the two
 * scanner pages.
 */
export function WeightSlider({
  label, value, min, max, step = 1, onChange, helperText, suffix,
}: WeightSliderProps) {
  const helper = typeof helperText === "function" ? helperText(value) : helperText;
  return (
    <div className="flex flex-col gap-2">
      <label className="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">
        {label}
      </label>
      <div className="flex items-center gap-3">
        <input
          type="range" min={min} max={max} step={step} value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="w-40 accent-[var(--color-primary)]"
        />
        <span className="text-xl font-bold text-white w-8">{value}</span>
      </div>
      {helper && (
        <p className="text-[11px] text-[var(--color-text-muted)]">
          {helper}
          {suffix && <span className="text-white/25"> {suffix}</span>}
        </p>
      )}
    </div>
  );
}
