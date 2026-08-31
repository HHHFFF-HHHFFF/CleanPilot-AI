import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

const baseProps = {
  fill: "none",
  stroke: "currentColor",
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  strokeWidth: 1.8,
  viewBox: "0 0 24 24",
};

export function LogoIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M8.2 12.2h7.6M9.4 9.2h.1M14.5 9.2h.1M9.3 15c1.8 1.2 3.6 1.2 5.4 0" />
      <path d="M12 3.5V2M4.7 18.2l-1.3 1.3M19.3 18.2l1.3 1.3" />
    </svg>
  );
}

export function SparklesIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <path d="m12 3 1.2 3.3L16.5 7.5l-3.3 1.2L12 12l-1.2-3.3-3.3-1.2 3.3-1.2L12 3Z" />
      <path d="m18.5 13 .8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8.8-2.2ZM5.5 13.5l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8L3 16l1.8-.7.7-1.8Z" />
    </svg>
  );
}

export function ShieldIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <path d="M12 3 5.5 5.7v5.7c0 4.1 2.6 7.7 6.5 9.6 3.9-1.9 6.5-5.5 6.5-9.6V5.7L12 3Z" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  );
}

export function DeviceIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <circle cx="12" cy="12" r="8.5" />
      <circle cx="12" cy="12" r="3.2" />
      <path d="M12 3.5v2M6 18l1.4-1.4M18 18l-1.4-1.4" />
    </svg>
  );
}

export function LocationIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0Z" />
      <circle cx="12" cy="10" r="2.3" />
    </svg>
  );
}

export function WeatherIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <path d="M8.5 18H17a4 4 0 0 0 .5-8 5.6 5.6 0 0 0-10.7 1.7A3.2 3.2 0 0 0 8.5 18Z" />
      <path d="M5 6.2 3.8 5M9 4V2.5M3 10H1.5" />
    </svg>
  );
}

export function SendIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <path d="m21 3-7.5 18-3.2-7.3L3 10.5 21 3Z" />
      <path d="m10.3 13.7 4.2-4.2" />
    </svg>
  );
}

export function StopIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <rect x="7" y="7" width="10" height="10" rx="1" />
    </svg>
  );
}

export function LogoutIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <path d="M10 5H5v14h5M14 8l4 4-4 4M8 12h10" />
    </svg>
  );
}

export function ChevronIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <path d="m8 10 4 4 4-4" />
    </svg>
  );
}

export function NewChatIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <path d="M12 20H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h8" />
      <path d="M16 3v6M13 6h6M8 9h2M8 13h7M8 17h5" />
    </svg>
  );
}

export function ChatIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <path d="M20 15a3 3 0 0 1-3 3H8l-4 3v-5a5 5 0 0 1-1-3V7a3 3 0 0 1 3-3h11a3 3 0 0 1 3 3v8Z" />
    </svg>
  );
}

export function TrashIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13M10 11v5M14 11v5" />
    </svg>
  );
}
