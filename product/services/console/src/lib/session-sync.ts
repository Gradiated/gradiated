import { usePlaygroundStore } from "@/store/playground";
import { useWorkspaceSelection } from "@/store/workspace-selection";

export const SESSION_REVISION_KEY = "gradiated-session-revision";
export const SESSION_SOURCE = crypto.randomUUID();

export const sessionChannel = () => {
  try {
    return new BroadcastChannel(SESSION_REVISION_KEY);
  } catch {
    return null;
  }
};

export const sessionRevision = () => {
  try {
    return localStorage.getItem(SESSION_REVISION_KEY);
  } catch {
    return null;
  }
};

export const resetIdentityState = () => {
  useWorkspaceSelection.getState().reset();
  usePlaygroundStore.getState().reset();
};

export const announceSessionChange = () => {
  try {
    localStorage.setItem(SESSION_REVISION_KEY, crypto.randomUUID());
  } catch {
    // BroadcastChannel still reaches other tabs when storage is unavailable.
  }
  const channel = sessionChannel();
  channel?.postMessage(SESSION_SOURCE);
  channel?.close();
};

export const switchConsoleIdentity = (destination: string) => {
  announceSessionChange();
  try {
    resetIdentityState();
  } finally {
    window.location.assign(destination);
  }
};
