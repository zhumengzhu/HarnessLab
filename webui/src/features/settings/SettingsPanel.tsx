type SettingsPanelProps = {
  loading: boolean;
  error: string | null;
  data: unknown;
};

export function SettingsPanel(props: SettingsPanelProps) {
  const { loading, error, data } = props;
  return (
    <section className="panel">
      <h2>Settings Snapshot</h2>
      {loading ? (
        <p>Loading...</p>
      ) : error ? (
        <p>Failed: {error}</p>
      ) : (
        <pre>{JSON.stringify(data, null, 2)}</pre>
      )}
    </section>
  );
}
