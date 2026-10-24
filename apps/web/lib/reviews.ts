"use client";

import type {
  CompleteReviewRequest,
  CompleteReviewResponse,
  ReviewDueListResponse,
  ReviewSessionResponse,
  StartReviewRequest,
} from "@codepilot/contracts";
import { apiFetch, ApiError } from "@/lib/api";

function devHeaders(userId: string): HeadersInit {
  return { "X-User-Id": userId };
}

export function startReview(
  userId: string,
  payload: StartReviewRequest,
): Promise<ReviewSessionResponse> {
  return apiFetch<ReviewSessionResponse>("/api/v1/reviews/sessions", {
    method: "POST",
    headers: devHeaders(userId),
    body: JSON.stringify(payload),
  });
}

export function completeReview(
  userId: string,
  sessionId: string,
  payload: CompleteReviewRequest,
): Promise<CompleteReviewResponse> {
  return apiFetch<CompleteReviewResponse>(`/api/v1/reviews/sessions/${sessionId}/complete`, {
    method: "POST",
    headers: devHeaders(userId),
    body: JSON.stringify(payload),
  });
}

export function listDueReviews(userId: string): Promise<ReviewDueListResponse> {
  return apiFetch<ReviewDueListResponse>("/api/v1/reviews/due", {
    headers: devHeaders(userId),
  });
}

export { ApiError };
