import { useSettings } from "@/components/SettingsProvider";
import type { FeatureFlags } from "./types";

/** Thin wrapper around SettingsProvider's context - settings are fetched
 *  once there (see components/SettingsProvider.tsx) and this just narrows
 *  that down to the four advanced-feature switches plus their setter, so
 *  pages and Header do not each need to know the shape of `Settings`. */
export function useFeatures(): FeatureFlags & {
  setFeatures: (next: FeatureFlags) => Promise<void>;
} {
  const { features, setFeatures } = useSettings();
  return { ...features, setFeatures };
}
