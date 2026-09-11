import { Avatar, Tooltip } from "antd";
import { Crown, ShieldCheck, Star, UserRound } from "lucide-react";
import type { Role } from "../types";

type UserAvatarProps = {
  username: string;
  avatar?: string;
  role?: Role | string;
  level?: number;
  size?: number;
  className?: string;
};

const levelInfo = (role: string | undefined, level: number | undefined) => {
  if (role === "admin") return { label: "管理员", className: "admin", icon: ShieldCheck };
  if (level === 2) return { label: "超级会员", className: "super", icon: Crown };
  if (level === 1) return { label: "会员用户", className: "member", icon: Star };
  return { label: "普通用户", className: "regular", icon: UserRound };
};

export function UserAvatar({ username, avatar, role, level, size = 36, className }: UserAvatarProps) {
  const info = levelInfo(role, level);
  const Icon = info.icon;
  return <span className={`user-avatar user-avatar-level-${info.className} ${className || ""}`} style={{ "--user-avatar-size": `${size}px` } as React.CSSProperties}>
    <Avatar size={size} src={avatar && avatar !== "default" ? avatar : undefined}>{username.slice(0, 1).toUpperCase()}</Avatar>
    <Tooltip title={info.label}>
      <span className={`user-avatar-badge user-avatar-badge-${info.className}`} aria-label={info.label}><Icon size={Math.max(10, Math.round(size * 0.38))} strokeWidth={2.5} /></span>
    </Tooltip>
  </span>;
}

// eslint-disable-next-line react-refresh/only-export-components
export const userLevelLabel = (role?: string, level?: number) => levelInfo(role, level).label;
