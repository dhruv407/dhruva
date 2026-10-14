export type Json = Record<string, any>;
export async function api(path: string, body?: unknown): Promise<any> {
  const response = await fetch(
    "/api" + path,
    body === undefined
      ? {}
      : body instanceof FormData
        ? { method: "POST", body }
        : {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          },
  );
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error(
      "The server returned an invalid response. Check the API service.",
    );
  }
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail),
    );
  return data;
}
export const branches = ["NV", "LN", "AR", "RO", "IK"];
export const locations = [...branches, "HO", "CZ"];
export const materialNames: Record<string, string> = {
  gold: "Gold",
  natural_diamond: "Natural diamonds",
  lab_diamond: "Lab-grown diamonds",
};
export const money = (paise: number | null | undefined) =>
  paise == null
    ? "—"
    : new Intl.NumberFormat("en-IN", {
        style: "currency",
        currency: "INR",
        maximumFractionDigits: 0,
      }).format(paise / 100);
export function download(data: unknown, name: string) {
  const u = URL.createObjectURL(
    new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = u;
  a.download = name;
  a.click();
  URL.revokeObjectURL(u);
}
