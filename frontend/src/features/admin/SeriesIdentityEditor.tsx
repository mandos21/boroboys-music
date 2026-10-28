import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { patch } from "../../api/client";
import { Button } from "../../components/ui/button";
import {
  Sheet,
  SheetTrigger,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "../../components/ui/sheet";
import { useToast } from "../../components/ui/ToastProvider";
import { errorMessage } from "./adminUtils";
import type { SeriesDetail } from "./types";

export function SeriesIdentityEditor({
  series,
  onSaved,
}: {
  series: SeriesDetail;
  onSaved: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [description, setDescription] = useState(series.description ?? "");
  const [cover, setCover] = useState(series.coverImageUrl ?? "");
  const [accent, setAccent] = useState(series.accentColor ?? "#15803d");
  const { showToast } = useToast();
  const save = useMutation({
    mutationFn: () =>
      patch(`/admin/series/${series.id}`, {
        description: description.trim() || null,
        cover_image_url: cover.trim() || null,
        accent_color: accent || null,
      }),
    onSuccess: () => {
      onSaved();
      setOpen(false);
      showToast({ title: "Series details saved" });
    },
  });
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger render={<Button variant="outline" />}>Edit series details</SheetTrigger>
      <SheetContent className="series-details-sheet">
        <SheetHeader>
          <SheetTitle>Series details</SheetTitle>
          <SheetDescription>Describe {series.name} and choose its appearance.</SheetDescription>
        </SheetHeader>
        <form
          className="admin-round-form"
          onSubmit={(event) => {
            event.preventDefault();
            save.mutate();
          }}
        >
          <label>
            Description
            <textarea
              maxLength={10000}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </label>
          <label>
            Cover image URL
            <input
              type="url"
              maxLength={1000}
              value={cover}
              onChange={(event) => setCover(event.target.value)}
            />
          </label>
          <label>
            Accent color
            <input
              pattern="#[0-9a-fA-F]{6}"
              value={accent}
              onChange={(event) => setAccent(event.target.value)}
            />
          </label>
          <Button type="submit" disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save series details"}
          </Button>
          {save.isError && (
            <p role="alert" className="error-message">
              {errorMessage(save.error)}
            </p>
          )}
        </form>
      </SheetContent>
    </Sheet>
  );
}
