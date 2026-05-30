import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App } from "./App";
import { applyUiTheme, resolveUiTheme } from "./features/shell/theme";
import { loadStoredThemeFamily, loadStoredUiTheme } from "./lib/uiPreferences";
import "./styles.css";
import "./styles/live-turn.css";

applyUiTheme(
  resolveUiTheme(loadStoredThemeFamily() ?? "claw", loadStoredUiTheme() ?? "system")
);

const queryClient = new QueryClient();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>
);
