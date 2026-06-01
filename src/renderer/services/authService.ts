import { OperatorIdentity } from "../../shared/types";
import { simsoftApi } from "../shared/api/simsoftApiClient";

export const authService = {
  getOperatorIdentity: (): Promise<OperatorIdentity> => simsoftApi.getOperatorIdentity(),
  loginGoogleOperator: (): Promise<OperatorIdentity> => simsoftApi.loginGoogleOperator(),
  logoutGoogleOperator: (): Promise<OperatorIdentity> => simsoftApi.logoutGoogleOperator()
};
