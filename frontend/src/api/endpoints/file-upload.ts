/**
 * endpoints/file-upload — file upload (priority 56).
 *
 * Extracted from endpoints.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for the shared client.
 */
import {
  api,
} from "../client";
// ---------- file upload (priority 56) ----------
// POST /uploads/upload takes a multipart FormData body (the axios `api` instance
// already attaches the bearer token), validates the content-type + size on the
// backend, and returns the URL the caller should persist on its own model
// (avatar/logo/…). The caller is responsible for saving the returned URL.
//
// The URL is served behind the authenticated download route (local backend:
// relative "uploads/files/{key}" joined to this instance's baseURL; S3/OSS:
// absolute https), so it must be rendered through <SecureImage>, NOT a plain
// <img src> — <img> cannot attach the Authorization header the route requires.

export interface UploadResponse {
  url: string; // e.g. uploads/files/{tenant}/{uuid}.png — render via <SecureImage>
  key: string; // the storage key (no original filename)
  size: number; // bytes
  content_type: string; // the validated MIME type
}

/**
 * Upload a single file via POST /uploads/upload. Returns the URL + metadata;
 * the caller persists the URL on its own record (e.g. TenantConfig.logo_url).
 *
 * Pass an optional onProgress callback (0–100) for a progress bar.
 */
export async function uploadFile(
  file: File,
  onProgress?: (percent: number) => void,
): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post<UploadResponse>("/uploads/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
    onUploadProgress: (evt) => {
      if (onProgress && evt.total) {
        onProgress(Math.round((evt.loaded / evt.total) * 100));
      }
    },
  });
  return data;
}

