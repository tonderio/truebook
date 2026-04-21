import { Role } from "@prisma/client";

const ROLE_HIERARCHY: Record<Role, number> = {
  SUPER_ADMIN: 4,
  ADMIN: 3,
  ACCOUNTANT: 2,
  VIEWER: 1,
};

const ACTION_MIN_ROLE: Record<string, Role> = {
  // Tenant management
  "tenant.manage": "SUPER_ADMIN",
  "tenant.viewAll": "SUPER_ADMIN",

  // Team management
  "team.invite": "ADMIN",
  "team.remove": "ADMIN",
  "team.changeRole": "ADMIN",

  // Process management
  "process.create": "ACCOUNTANT",
  "process.run": "ACCOUNTANT",
  "process.delete": "ADMIN",
  "process.view": "VIEWER",

  // Files
  "file.upload": "ACCOUNTANT",
  "file.delete": "ACCOUNTANT",

  // Results
  "results.view": "VIEWER",
  "results.export": "ACCOUNTANT",

  // Settings
  "settings.manage": "ADMIN",
  "integrations.manage": "ADMIN",
  "audit.view": "ADMIN",

  // Schedules
  "schedule.manage": "ACCOUNTANT",

  // AI
  "ai.chat": "VIEWER",
};

export function hasPermission(userRole: Role, action: string): boolean {
  const minRole = ACTION_MIN_ROLE[action];
  if (!minRole) return false;
  return ROLE_HIERARCHY[userRole] >= ROLE_HIERARCHY[minRole];
}

export function getRoleLabel(role: Role): string {
  const labels: Record<Role, string> = {
    SUPER_ADMIN: "Super Admin",
    ADMIN: "Administrador",
    ACCOUNTANT: "Contador",
    VIEWER: "Observador",
  };
  return labels[role];
}
