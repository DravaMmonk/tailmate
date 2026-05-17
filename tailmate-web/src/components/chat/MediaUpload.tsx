import { Paperclip, X } from "lucide-react";
import { useRef } from "react";
import { Button } from "../ui/Button";

interface MediaUploadProps {
  file: File | null;
  onFileChange: (file: File | null) => void;
}

export function MediaUpload({ file, onFileChange }: MediaUploadProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);

  return (
    <div className="flex items-center gap-2">
      <input
        ref={inputRef}
        hidden
        type="file"
        accept="image/*,video/*,audio/*"
        onChange={(event) => onFileChange(event.target.files?.[0] ?? null)}
      />
      <Button
        type="button"
        variant="ghost"
        className="h-11 w-11 rounded-2xl px-0"
        onClick={() => inputRef.current?.click()}
      >
        <Paperclip className="h-4 w-4" />
      </Button>
      {file ? (
        <div className="organic-status-chip flex items-center gap-2 px-3 py-2 text-xs font-semibold text-[var(--organic-muted-text)]">
          <span className="max-w-[140px] truncate">{file.name}</span>
          <button
            type="button"
            onClick={() => onFileChange(null)}
            className="text-[var(--organic-foreground)]"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      ) : null}
    </div>
  );
}
