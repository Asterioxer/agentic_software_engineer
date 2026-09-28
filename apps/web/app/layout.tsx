import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Agentic Software Engineer",
  description: "A guarded and auditable AI software engineering control plane.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
