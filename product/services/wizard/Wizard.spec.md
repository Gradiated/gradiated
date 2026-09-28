# Wizard

The customer wizard CLI: it signs in, creates an API key and configures local coding agents to use Gradiated.

## entrances

- install: a person signs in, gets an API key and configures their coding agents
  handler: runInstall in src/commands/install.ts
  trust: local-user
  control: none — it acts only for the person who runs it, with their own session and files
- uninstall: a person removes the Gradiated configuration from their coding agents
  handler: runUninstall in src/commands/uninstall.ts
  trust: local-user
  control: none — it edits only the running person's own agent configuration files

## invariants
