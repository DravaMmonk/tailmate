import { SendHorizontal } from "lucide-react";
import { useState } from "react";
import { Button } from "../ui/Button";
import { Textarea } from "../ui/Textarea";
import { MediaUpload } from "./MediaUpload";

interface ChatInputProps {
  disabled?: boolean;
  onSubmit: (payload: { text: string; file: File | null }) => Promise<void>;
}

export function ChatInput({ disabled, onSubmit }: ChatInputProps) {
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);

  async function handleSubmit() {
    const normalizedText = text.trim();
    if (!normalizedText && !file) {
      return;
    }
    await onSubmit({
      text: normalizedText || "Please sanitise and store this upload.",
      file,
    });
    setText("");
    setFile(null);
  }

  return (
    <div className="organic-panel organic-panel-soft p-4">
      <Textarea
        value={text}
        disabled={disabled}
        onChange={(event) => setText(event.target.value)}
        placeholder="Ask about symptoms, food changes, routines, or anything that might matter."
        className="min-h-[120px] resize-none"
      />
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <MediaUpload file={file} onFileChange={setFile} />
        <Button type="button" onClick={() => void handleSubmit()} disabled={disabled}>
          Send
          <SendHorizontal className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
