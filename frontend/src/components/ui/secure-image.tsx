import { useEffect, useState } from "react";

import { api } from "@/api/client";
import { cn } from "@/lib/utils";

/**
 * Renders an <img> whose src requires authentication.
 *
 * The upload route (priority 56) returns URLs that are served by the
 * authenticated download endpoint ``GET /uploads/files/{key}`` (local backend)
 * or an absolute https URL (S3/OSS). Neither can go straight into ``<img src>``
 * because ``<img>`` cannot attach an ``Authorization`` header, and the download
 * route rejects unauthenticated requests with 401.
 *
 * This component fetches the bytes through the authenticated ``api`` axios
 * instance as a Blob, makes a temporary object URL, and feeds that to ``<img>``.
 * The object URL is revoked on src change / unmount so we never leak blob URLs.
 *
 * For a purely local preview (an ``objectURL`` you already created from a
 * selected ``File``), use a plain ``<img>`` — the bytes are already in memory
 * and need no auth.
 */
export interface SecureImageProps {
  /** Authenticated URL — relative (``uploads/files/...``) or absolute (https). */
  src: string | null | undefined;
  alt?: string;
  className?: string;
}

export function SecureImage({ src, alt = "", className }: SecureImageProps) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!src) {
      setObjectUrl(null);
      return;
    }
    let revoked = false;
    let createdUrl: string | null = null;
    // axios resolves relative URLs against baseURL (/api/v1) and absolute URLs
    // untouched, so both the local ("uploads/files/…") and S3 ("https://…")
    // shapes work with one call.
    api
      .get<Blob>(src, { responseType: "blob" })
      .then((resp) => {
        if (revoked) return;
        createdUrl = URL.createObjectURL(resp.data);
        setObjectUrl(createdUrl);
      })
      .catch(() => {
        // 401/404/network — leave the image blank rather than surfacing a
        // broken-image icon; callers can layer a fallback via a sibling node.
        if (!revoked) setObjectUrl(null);
      });
    return () => {
      revoked = true;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [src]);

  if (!objectUrl) return null;
  // eslint-disable-next-line jsx-a11y/alt-text -- alt defaults to "" above
  return <img src={objectUrl} alt={alt} className={cn(className)} />;
}
