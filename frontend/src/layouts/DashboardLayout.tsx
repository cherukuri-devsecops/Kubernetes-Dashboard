import { Outlet } from "react-router-dom";

import { Footer } from "@/layouts/Footer";
import { Sidebar } from "@/layouts/Sidebar";
import { Header } from "@/layouts/Header";

export function DashboardLayout() {
  return (
    <div className="min-h-screen bg-app text-content-primary">
      <Sidebar />
      <div className="flex min-h-screen flex-col lg:pl-72">
        <Header />
        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <Outlet />
        </main>
        <Footer />
      </div>
    </div>
  );
}
