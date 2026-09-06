import { ApiError } from "../../api/client";

export function errorMessage(error: unknown): string | null {
  return error instanceof ApiError ? error.message : null;
}
