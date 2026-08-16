import { zodResolver } from "@hookform/resolvers/zod";
import { useNavigate } from "@tanstack/react-router";
import { LoaderCircle } from "lucide-react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { authClient } from "@/auth";
import { Brand } from "@/components/brand";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Field,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";

const LoginSchema = z.object({
  email: z.email("Enter a valid email address."),
  password: z.string().min(1, "Enter your password."),
});

type LoginValues = z.infer<typeof LoginSchema>;

export const LoginPage = () => {
  const navigate = useNavigate();
  const form = useForm<LoginValues>({
    resolver: zodResolver(LoginSchema),
    defaultValues: { email: "dev@gradiated.com", password: "1234" },
  });

  const submit = async (values: LoginValues) => {
    const result = await authClient.signIn.email(values);
    if (result.error) {
      form.setError("root", {
        message: "That email and password do not match.",
      });
      return;
    }
    await navigate({ to: "/api-keys" });
  };

  return (
    <main className="flex min-h-svh flex-col items-center justify-center bg-muted p-6 md:p-10">
      <div className="w-full max-w-sm md:max-w-4xl">
        <div className="mb-6">
          <Brand />
        </div>
        <Card className="overflow-hidden p-0 shadow-xl shadow-black/5">
          <CardContent className="grid p-0 md:grid-cols-2">
            <form className="p-6 md:p-9" onSubmit={form.handleSubmit(submit)}>
              <FieldGroup>
                <div className="flex flex-col items-center gap-2 text-center">
                  <h1 className="text-2xl font-bold tracking-tight">Sign in</h1>
                </div>
                <Field data-invalid={Boolean(form.formState.errors.email)}>
                  <FieldLabel htmlFor="email">Email</FieldLabel>
                  <Input
                    id="email"
                    type="email"
                    autoComplete="email"
                    {...form.register("email")}
                  />
                  {form.formState.errors.email ? (
                    <FieldError errors={[form.formState.errors.email]} />
                  ) : null}
                </Field>
                <Field data-invalid={Boolean(form.formState.errors.password)}>
                  <FieldLabel htmlFor="password">Password</FieldLabel>
                  <Input
                    id="password"
                    type="password"
                    autoComplete="current-password"
                    {...form.register("password")}
                  />
                  {form.formState.errors.password ? (
                    <FieldError errors={[form.formState.errors.password]} />
                  ) : null}
                </Field>
                {form.formState.errors.root?.message ? (
                  <FieldError>{form.formState.errors.root.message}</FieldError>
                ) : null}
                <Field>
                  <Button
                    className="w-full"
                    disabled={form.formState.isSubmitting}
                    type="submit"
                  >
                    {form.formState.isSubmitting ? (
                      <LoaderCircle className="size-4 animate-spin" />
                    ) : null}
                    Continue
                  </Button>
                </Field>
              </FieldGroup>
            </form>
            <div className="relative hidden min-h-[520px] overflow-hidden bg-[#181914] text-white md:block">
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_75%_20%,rgba(215,243,110,0.18),transparent_28%),linear-gradient(145deg,transparent_42%,rgba(255,255,255,0.04)_42%)]" />
              <div className="absolute -bottom-28 -right-24 size-96 rounded-full border border-[#d7f36e]/30" />
              <div className="absolute -bottom-10 right-24 size-52 rounded-full border border-white/10" />
              <div className="relative flex h-full flex-col p-9">
                <div className="mt-auto space-y-4">
                  <p className="text-3xl font-medium leading-tight tracking-[-0.035em]">
                    Infrastructure that makes every token count.
                  </p>
                  <p className="max-w-sm text-sm leading-6 text-white/55">
                    Deploy optimized open-weight models at the lowest cost.
                  </p>
                </div>
                <p className="mt-12 font-mono text-[10px] text-white/35">
                  gradiated.com
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </main>
  );
};
