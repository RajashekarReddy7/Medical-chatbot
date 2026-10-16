/* Render **bold** and line breaks safely, without injecting HTML. */
export default function RichText({ text }) {
  return (
    <>
      {String(text ?? "").split("\n").map((line, i) => (
        <p key={i} className={line.trim() ? undefined : "gap"}>
          {line.split(/(\*\*[^*]+\*\*)/g).map((part, j) =>
            part.startsWith("**") && part.endsWith("**") ? (
              <strong key={j}>{part.slice(2, -2)}</strong>
            ) : (
              part
            )
          )}
        </p>
      ))}
    </>
  );
}
