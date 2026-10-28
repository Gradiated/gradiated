import { useMutation } from "@tanstack/react-query";
import { useId, useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";

export const NameSetting = ({
  label,
  savedName,
  canEdit,
  onSave,
  successMessage,
}: {
  label: string;
  savedName: string;
  canEdit: boolean;
  onSave: (name: string) => Promise<void>;
  successMessage: string;
}) => {
  const id = useId();
  const [name, setName] = useState(savedName);
  const save = useMutation({
    mutationFn: onSave,
    onSuccess: () => toast.success(successMessage),
    meta: { errorMessage: "The name could not be saved." },
  });
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (canEdit && name.trim() && name.trim() !== savedName && !save.isPending)
      save.mutate(name.trim());
  };

  return (
    <form
      className="max-w-xl space-y-5 rounded-xl border bg-card p-6"
      onSubmit={submit}
    >
      <Field>
        <FieldLabel htmlFor={id}>{label}</FieldLabel>
        <Input
          id={id}
          name="scopeLabel"
          value={name}
          onChange={(event) => setName(event.target.value)}
          maxLength={200}
          required
          autoComplete="off"
          data-1p-ignore="true"
          disabled={!canEdit || save.isPending}
        />
      </Field>
      <Button
        type="submit"
        disabled={
          !canEdit ||
          save.isPending ||
          !name.trim() ||
          name.trim() === savedName
        }
      >
        {save.isPending ? "Saving…" : "Save changes"}
      </Button>
    </form>
  );
};
