import { useCallback, useEffect, useRef, useState } from "react";
import { ValidationOverlayState } from "../../features/posting/model/postingViewModel";

export function useDashboardFeedback() {
  const [toastMessage, setToastMessage] = useState("");
  const [validationOverlay, setValidationOverlay] = useState<ValidationOverlayState>(null);
  const validationOverlayTimer = useRef<number | null>(null);
  const toastTimer = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (validationOverlayTimer.current) window.clearTimeout(validationOverlayTimer.current);
      if (toastTimer.current) window.clearTimeout(toastTimer.current);
    };
  }, []);

  const showToast = useCallback((text: string) => {
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
    setToastMessage(text);
    toastTimer.current = window.setTimeout(() => {
      setToastMessage("");
      toastTimer.current = null;
    }, 1800);
  }, []);

  const showValidationOverlay = useCallback((overlay: Exclude<ValidationOverlayState, null>, autoHide = false) => {
    if (validationOverlayTimer.current) window.clearTimeout(validationOverlayTimer.current);
    setValidationOverlay(overlay);
    if (autoHide) {
      validationOverlayTimer.current = window.setTimeout(() => {
        setValidationOverlay(null);
        validationOverlayTimer.current = null;
      }, 1500);
    }
  }, []);

  return {
    toastMessage,
    validationOverlay,
    showToast,
    showValidationOverlay
  };
}
