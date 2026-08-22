import { useId } from 'react';
import { cn } from '@/lib/utils';

export function EleVideoMark({ className, title = 'EleVideo' }) {
  const gradientId = `elevideo-gradient-${useId().replace(/:/g, '')}`;
  const playGradientId = `elevideo-play-${useId().replace(/:/g, '')}`;

  return (
    <svg
      viewBox="0 0 64 64"
      role="img"
      aria-label={title}
      className={cn('shrink-0', className)}
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <linearGradient id={gradientId} x1="11" y1="10" x2="54" y2="54" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#9333EA" />
          <stop offset="0.52" stopColor="#4F46E5" />
          <stop offset="1" stopColor="#06B6D4" />
        </linearGradient>
        <linearGradient id={playGradientId} x1="25" y1="25" x2="41" y2="42" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#A855F7" />
          <stop offset="0.5" stopColor="#6366F1" />
          <stop offset="1" stopColor="#0EA5E9" />
        </linearGradient>
      </defs>

      {/* Video frame with an intentional break where the image dissolves into pixels. */}
      <path
        d="M24 14H18C12.477 14 8 18.477 8 24V46C8 51.523 12.477 56 18 56H46C51.523 56 56 51.523 56 46V24C56 18.477 51.523 14 46 14H43"
        fill="none"
        stroke={`url(#${gradientId})`}
        strokeWidth="4"
        strokeLinecap="round"
      />

      {/* Film perforations: enough to read as video, simple enough to survive at favicon size. */}
      <g fill={`url(#${gradientId})`}>
        <rect x="11.5" y="24" width="3.5" height="4.5" rx="1.3" />
        <rect x="11.5" y="31.5" width="3.5" height="4.5" rx="1.3" />
        <rect x="11.5" y="39" width="3.5" height="4.5" rx="1.3" />
        <rect x="49" y="24" width="3.5" height="4.5" rx="1.3" />
        <rect x="49" y="31.5" width="3.5" height="4.5" rx="1.3" />
        <rect x="49" y="39" width="3.5" height="4.5" rx="1.3" />
      </g>

      {/* Playback is the center of the product, while the pixels hint at transformation/AI processing. */}
      <path
        d="M26 25.7C26 24.55 27.25 23.83 28.25 24.41L41.75 32.21C42.75 32.79 42.75 34.23 41.75 34.81L28.25 42.61C27.25 43.19 26 42.47 26 41.32V25.7Z"
        fill={`url(#${playGradientId})`}
      />
      <rect x="25" y="49" width="14" height="2.5" rx="1.25" fill={`url(#${gradientId})`} opacity="0.85" />

      <g fill={`url(#${gradientId})`}>
        <rect x="27" y="7" width="5.5" height="5.5" rx="1.4" />
        <rect x="34.5" y="3.5" width="4.5" height="4.5" rx="1.2" opacity="0.9" />
        <rect x="36.5" y="9.5" width="3.5" height="3.5" rx="1" opacity="0.75" />
      </g>
    </svg>
  );
}

export function EleVideoLogo({
  className,
  markClassName = 'h-9 w-9',
  wordmarkClassName,
  tagline,
  compact = false,
}) {
  return (
    <div className={cn('flex items-center gap-3', className)}>
      <div className="relative shrink-0">
        <div
          className="absolute inset-1 rounded-xl bg-gradient-to-br from-violet-500/35 via-indigo-500/25 to-cyan-400/35 blur-md"
          aria-hidden="true"
        />
        <EleVideoMark className={cn('relative drop-shadow-sm', markClassName)} />
      </div>

      {!compact && (
        <div className="flex min-w-0 flex-col">
          <span
            className={cn(
              'font-outfit text-xl font-semibold tracking-[0.04em] text-slate-950 dark:text-slate-50',
              wordmarkClassName
            )}
          >
            Ele<span className="bg-gradient-to-r from-violet-500 via-indigo-500 to-cyan-400 bg-clip-text text-transparent">V</span>ideo
          </span>
          {tagline && (
            <span className="-mt-0.5 hidden text-xs text-muted-foreground sm:block">
              {tagline}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
