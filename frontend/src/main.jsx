
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import "./index.css";

// Sem React.StrictMode: em desenvolvimento ele monta as telas duas vezes, o que abriria
// duas sessões de voz com a OpenAI e duas leituras do medidor de pressão ao mesmo tempo.
ReactDOM.createRoot(document.getElementById("root")).render(<App />);
