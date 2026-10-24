"use client";

import type {
  CompleteReviewRequest,
  CompleteReviewResponse,
  ReviewDueListResponse,
  ReviewSessionResponse,
  StartReviewRequest,
} from "@codepilot/contracts";
import { ApiError, apiFetch } from "@/lib/api";

export function startReview(payload: StartReviewRequest): Promise<ReviewSessionResponse> {
  return apiFetch<ReviewSessionResponse>("/api/v1/reviews/sessions", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function completeReview(
  sessionId: string,
  payload: CompleteReviewRequest,
): Promise<CompleteReviewResponse> {
  return apiFetch<CompleteReviewResponse>(`/api/v1/reviews/sessions/${sessionId}/complete`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listDueReviews(
  mode: "due" | "upcoming" = "due",
): Promise<ReviewDueListResponse> {
  return apiFetch<ReviewDueListResponse>(`/api/v1/reviews/due?mode=${mode}`);
}

export { ApiError };
