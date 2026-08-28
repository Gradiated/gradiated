import { zodResolver } from "@hookform/resolvers/zod";
import { LoaderCircle, MailCheck } from "lucide-react";
import { useForm } from "react-hook-form";
import { useState } from "react";
import { z } from "zod";

import { authClient } from "@/auth";
import { Brand } from "@/components/brand";
import { GitHubIcon, GoogleIcon } from "@/components/icons";
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
});

type LoginValues = z.infer<typeof LoginSchema>;
type SocialProvider = "github" | "google";

export const LoginPage = () => {
  const callbackError = new URLSearchParams(window.location.search).get(
    "error",
  );
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [socialPending, setSocialPending] = useState<SocialProvider | null>(
    null,
  );
  const form = useForm<LoginValues>({
    resolver: zodResolver(LoginSchema),
    defaultValues: { email: "" },
  });

  const submit = async (values: LoginValues) => {
    const callbackURL = `${window.location.origin}/api-keys`;
    const result = await authClient.signIn.magicLink({
      email: values.email,
      callbackURL,
      newUserCallbackURL: callbackURL,
      errorCallbackURL: `${window.location.origin}/login`,
    });
    if (result.error) {
      form.setError("root", {
        message: "We could not send the sign-in link. Try again.",
      });
      return;
    }
    setSentTo(values.email);
  };

  const signInWithSocial = async (provider: SocialProvider) => {
    setSocialPending(provider);
    const result = await authClient.signIn.social({
      provider,
      callbackURL: `${window.location.origin}/api-keys`,
      errorCallbackURL: `${window.location.origin}/login`,
      newUserCallbackURL: `${window.location.origin}/api-keys`,
    });
    if (result?.error) {
      setSocialPending(null);
      form.setError("root", {
        message: `${provider === "google" ? "Google" : "GitHub"} sign-in could not start. Try again.`,
      });
    }
  };

  return (
    <main className="flex min-h-svh flex-col items-center justify-center bg-muted p-6 md:p-10">
      <div className="w-full max-w-sm">
        <div className="mb-6">
          <Brand />
        </div>
        <Card className="overflow-hidden p-0 shadow-xl shadow-black/5">
          <CardContent className="p-0">
            <form className="p-6 md:p-9" onSubmit={form.handleSubmit(submit)}>
              <FieldGroup>
                <div className="flex flex-col items-center gap-2 text-center">
                  <h1 className="text-2xl font-bold tracking-tight">Sign in</h1>
                  <p className="text-sm text-muted-foreground">
                    Create an account or continue to your workspace.
                  </p>
                </div>
                <div className="flex flex-col gap-3">
                  <Button
                    className="w-full gap-2.5"
                    disabled={
                      socialPending !== null || form.formState.isSubmitting
                    }
                    onClick={() => void signInWithSocial("google")}
                    type="button"
                    variant="outline"
                  >
                    {socialPending === "google" ? (
                      <LoaderCircle className="size-4 animate-spin" />
                    ) : (
                      <GoogleIcon className="size-4" />
                    )}
                    Continue with Google
                  </Button>
                  <Button
                    className="w-full gap-2.5"
                    disabled={
                      socialPending !== null || form.formState.isSubmitting
                    }
                    onClick={() => void signInWithSocial("github")}
                    type="button"
                    variant="outline"
                  >
                    {socialPending === "github" ? (
                      <LoaderCircle className="size-4 animate-spin" />
                    ) : (
                      <GitHubIcon className="size-4" />
                    )}
                    Continue with GitHub
                  </Button>
                </div>
                <div className="flex items-center gap-3 text-xs uppercase tracking-wider text-muted-foreground">
                  <div className="h-px flex-1 bg-border" />
                  or
                  <div className="h-px flex-1 bg-border" />
                </div>
                {sentTo ? (
                  <div className="rounded-lg border bg-muted/50 p-4 text-center">
                    <MailCheck className="mx-auto mb-3 size-6" />
                    <p className="font-medium">Check your email</p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      We sent a sign-in link to {sentTo}.
                    </p>
                    <Button
                      className="mt-3"
                      onClick={() => setSentTo(null)}
                      type="button"
                      variant="ghost"
                    >
                      Use another email
                    </Button>
                  </div>
                ) : (
                  <>
                    <Field data-invalid={Boolean(form.formState.errors.email)}>
                      <FieldLabel htmlFor="email">Email</FieldLabel>
                      <Input
                        id="email"
                        type="email"
                        autoComplete="email"
                        placeholder="you@company.com"
                        {...form.register("email")}
                      />
                      {form.formState.errors.email ? (
                        <FieldError errors={[form.formState.errors.email]} />
                      ) : null}
                    </Field>
                    <Field>
                      <Button
                        className="w-full"
                        disabled={
                          form.formState.isSubmitting || socialPending !== null
                        }
                        type="submit"
                      >
                        {form.formState.isSubmitting ? (
                          <LoaderCircle className="size-4 animate-spin" />
                        ) : null}
                        Email me a sign-in link
                      </Button>
                    </Field>
                  </>
                )}
                {form.formState.errors.root?.message ? (
                  <FieldError>{form.formState.errors.root.message}</FieldError>
                ) : null}
                {callbackError ? (
                  <FieldError>Sign-in failed. Try again.</FieldError>
                ) : null}
              </FieldGroup>
            </form>
          </CardContent>
        </Card>
      </div>
    </main>
  );
};
