import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import MythApp from "./myth/MythApp";
import "./myth/myth.css";
import "./styles.css";

const root = document.getElementById("root");
if (!root) throw new Error("缺少 #root 挂载节点");

const Entry = window.location.pathname === "/myth" || window.location.pathname.startsWith("/myth/") ? MythApp : App;

createRoot(root).render(<StrictMode><Entry /></StrictMode>);
