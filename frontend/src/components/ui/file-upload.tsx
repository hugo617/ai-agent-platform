import { useCallback, useRef, useState } from "react";
import { UploadCloud, X } from "lucide-react";

import { cn } from "@/lib/utils";
import { apiErrorMessage } from "@/api/client";
import { uploadFile } from "@/api/endpoints";

/**
 * Reusable file upload component (priority 56).
 *
 * Provides a click-or-drag-drop zone, an image preview when the file is an
 * image, and an upload progress bar. Calls POST /uploads/upload (multipart
 * FormData) and reports the resulting URL back to the parent via onUploaded.
 *
 * The parent owns the persisted URL — this component is purely the upload
 * affordance. It is consumer-agnostic (avatar / logo / document …), so it
 * validates nothing about how the URL is later used.
 *
 * Security: the backend enforces the content-type whitelist + size cap; this
 * component additionally accepts an `accept` prop so the OS file picker nudges
 * the user toward the right kind of file, and a `maxSizeMb` client-side guard
 * for a snappier "too big" message before the round-trip.
 */

export interface FileUploadProps {
  /** Called with the uploaded URL once the backend returns. */
  onUploaded: (url: string) => void;
  /** Optional: controlled current value (e.g. an existing logo URL) for preview. */
  value?: string | null;
  /** accepted MIME types passed to the <input accept=> (OS picker hint only). */
  accept?: string;
  /** client-side size guard (MB); backend still enforces its own cap. */
  maxSizeMb?: number;
  /** show an image thumbnail when the file/URL is an image. Default true. */
  preview?: boolean;
  className?: string;
  disabled?: boolean;
  /** accessible label for the drop zone. */
  label?: string;
}

interface UploadState {
  status: "idle" | "uploading" | "error";
  progress: number;
  error: string | null;
}

const INITIAL_STATE: UploadState = {
  status: "idle",
  progress: 0,
  error: null,
};

const IMAGE_RE = /^image\//;

export function FileUpload({
  onUploaded,
  value,
  accept = "image/*",
  maxSizeMb,
  preview = true,
  className,
  disabled = false,
  label = "点击或拖拽文件到此处上传",
}: FileUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [state, setState] = useState<UploadState>(INITIAL_STATE);
  // The object URL for the currently-picked file's preview (revoked on change).
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  const doUpload = useCallback(
    async (file: File) => {
      // Client-side size guard: fail fast with a readable message instead of
      // streaming the whole body to the backend only to get a 413.
      if (maxSizeMb && file.size > maxSizeMb * 1024 * 1024) {
        setState({
          status: "error",
          progress: 0,
          error: `文件过大(超过 ${maxSizeMb} MB)`,
        });
        return;
      }
      setState({ status: "uploading", progress: 0, error: null });
      try {
        const resp = await uploadFile(file, (p) =>
          setState({ status: "uploading", progress: p, error: null }),
        );
        setState(INITIAL_STATE);
        onUploaded(resp.url);
      } catch (err) {
        setState({
          status: "error",
          progress: 0,
          error: apiErrorMessage(err),
        });
      }
    },
    [maxSizeMb, onUploaded],
  );

  const handleFiles = useCallback(
    (files: FileList | null) => {
      if (!files || files.length === 0) return;
      const file = files[0];
      // Build a local preview URL for the picked image so the user sees it
      // immediately, even before the upload completes.
      if (preview && IMAGE_RE.test(file.type)) {
        setPreviewUrl((prev) => {
          if (prev) URL.revokeObjectURL(prev);
          return URL.createObjectURL(file);
        });
      }
      void doUpload(file);
    },
    [doUpload, preview],
  );

  const onDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      handleFiles(e.dataTransfer.files);
    },
    [handleFiles],
  );

  const shownPreview = previewUrl ?? (preview && value ? value : null);

  return (
    <div className={cn("space-y-2", className)}>
      <div
        role="button"
        tabIndex={0}
        aria-label={label}
        aria-disabled={disabled}
        onClick={() => {
          if (!disabled) inputRef.current?.click();
        }}
        onKeyDown={(e) => {
          if ((e.key === "Enter" || e.key === " ") && !disabled) {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDragOver={(e) => e.preventDefault()}
        onDrop={onDrop}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-md border border-dashed border-input bg-background px-4 py-6 text-center text-sm text-muted-foreground transition-colors hover:border-primary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
          disabled && "pointer-events-none opacity-50",
        )}
      >
        {shownPreview ? (
          <div className="relative">
            <img
              src={shownPreview}
              alt="预览"
              className="max-h-32 max-w-full rounded object-contain"
            />
            {state.status !== "uploading" && (
              <button
                type="button"
                aria-label="清除预览"
                onClick={(e) => {
                  e.stopPropagation();
                  setPreviewUrl((prev) => {
                    if (prev) URL.revokeObjectURL(prev);
                    return null;
                  });
                  onUploaded("");
                }}
                className="absolute -right-2 -top-2 rounded-full bg-destructive p-0.5 text-destructive-foreground shadow"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        ) : (
          <>
            <UploadCloud className="h-8 w-8 text-muted-foreground" />
            <span>{label}</span>
          </>
        )}
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>

      {state.status === "uploading" && (
        <div className="space-y-1">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-secondary">
            <div
              className="h-full bg-primary transition-all"
              style={{ width: `${state.progress}%` }}
            />
          </div>
          <p className="text-xs text-muted-foreground">上传中… {state.progress}%</p>
        </div>
      )}

      {state.status === "error" && (
        <p className="text-xs text-destructive">{state.error}</p>
      )}
    </div>
  );
}
