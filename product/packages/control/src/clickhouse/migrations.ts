export const identifierPattern = /^[A-Za-z_][A-Za-z0-9_]*$/;

const migrationFilePattern = /^\d{4}_[a-z0-9_]+\.sql$/;

export type Migration = {
  checksum: string;
  name: string;
  query: string;
};

export const safeIdentifier = (name: string, value: string): string => {
  if (!identifierPattern.test(value)) {
    throw new Error(`${name} must be a ClickHouse identifier`);
  }

  return `\`${value}\``;
};

export const selectMigrationFiles = (names: string[]): string[] =>
  names.filter((name) => migrationFilePattern.test(name)).sort();

export const pendingMigrations = (
  migrations: Migration[],
  applied: ReadonlyMap<string, string>,
): Migration[] =>
  migrations.filter((migration) => {
    const appliedChecksum = applied.get(migration.name);
    if (appliedChecksum === undefined) return true;

    if (appliedChecksum !== migration.checksum) {
      throw new Error(`Applied migration changed: ${migration.name}`);
    }

    return false;
  });
