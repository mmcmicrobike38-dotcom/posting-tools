import { useCallback, useEffect, useState } from "react";
import { AppStatus, DuplicateHistoryStatus, HealthCheckResult, OperatorIdentity } from "../../../shared/types";
import { authService } from "../../services/authService";
import { simsoftApi } from "../../shared/api/simsoftApiClient";
import { operatorError } from "../../utils/errors";

export function useAppBootstrap(setMessage: (message: string) => void) {
  const [status, setStatus] = useState<AppStatus | null>(null);
  const [duplicateStatus, setDuplicateStatus] = useState<DuplicateHistoryStatus | null>(null);
  const [healthCheck, setHealthCheck] = useState<HealthCheckResult | null>(null);
  const [operatorIdentity, setOperatorIdentity] = useState<OperatorIdentity | null>(null);

  const refreshStatus = useCallback(() => {
    simsoftApi.getStatus().then(setStatus).catch((error) => setMessage(operatorError(error, "App status could not be loaded.")));
  }, [setMessage]);

  useEffect(() => {
    refreshStatus();
    simsoftApi
      .getDuplicateHistoryStatus()
      .then(setDuplicateStatus)
      .catch((error) => setMessage(operatorError(error, "Duplicate history status could not be loaded.")));
    authService
      .getOperatorIdentity()
      .then(setOperatorIdentity)
      .catch((error) => setMessage(operatorError(error, "Google operator status could not be loaded.")));
  }, [refreshStatus, setMessage]);

  return {
    status,
    setStatus,
    refreshStatus,
    duplicateStatus,
    setDuplicateStatus,
    healthCheck,
    setHealthCheck,
    operatorIdentity,
    setOperatorIdentity
  };
}
