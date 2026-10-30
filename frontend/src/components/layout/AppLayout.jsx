import Sidebar from "./Sidebar";

export default function AppLayout({ children }) {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 min-w-0 px-8 pt-8 pb-4">{children}</main>
    </div>
  );
}
