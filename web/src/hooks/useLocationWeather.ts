import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, getCityWeather, getLocationWeather } from "../lib/api";
import type { LocationProfile } from "../types";

export type LocationStatus = "requesting" | "loading" | "ready" | "fallback" | "error";

export function useLocationWeather(
  token: string,
  fallbackCity: string,
  onUnauthorized: () => void,
) {
  const [profile, setProfile] = useState<LocationProfile | null>(null);
  const [status, setStatus] = useState<LocationStatus>("requesting");
  const initialized = useRef(false);

  const loadFallbackWeather = useCallback(async () => {
    try {
      const weather = await getCityWeather(token, fallbackCity);
      setProfile(weather);
      setStatus("fallback");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        onUnauthorized();
        return;
      }
      setStatus("error");
    }
  }, [fallbackCity, onUnauthorized, token]);

  const refresh = useCallback(() => {
    if (!navigator.geolocation) {
      setStatus("loading");
      void loadFallbackWeather();
      return;
    }
    setStatus("requesting");
    navigator.geolocation.getCurrentPosition(
      async ({ coords }) => {
        setStatus("loading");
        try {
          const weather = await getLocationWeather(token, coords.latitude, coords.longitude);
          setProfile(weather);
          setStatus("ready");
        } catch (error) {
          if (error instanceof ApiError && error.status === 401) {
            onUnauthorized();
            return;
          }
          setStatus("error");
        }
      },
      () => {
        setStatus("loading");
        void loadFallbackWeather();
      },
      { enableHighAccuracy: false, timeout: 10_000, maximumAge: 300_000 },
    );
  }, [loadFallbackWeather, onUnauthorized, token]);

  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    refresh();
  }, [refresh]);

  return { profile, status, refresh };
}
