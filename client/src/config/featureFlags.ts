function isEnabled(rawValue: string | undefined, defaultValue: boolean): boolean {
  if (!rawValue) {
    return defaultValue;
  }
  const normalized = rawValue.trim().toLowerCase();
  return !["0", "false", "off", "no"].includes(normalized);
}

export const featureFlags = {
  creationStudioEnabled: isEnabled(import.meta.env.VITE_CREATION_STUDIO_ENABLED, true),
  worldWorkspaceEnabled: isEnabled(import.meta.env.VITE_WORLD_WORKSPACE_ENABLED, true),
  worldVisEnabled: isEnabled(import.meta.env.VITE_WORLD_VIS_ENABLED, true),
};
