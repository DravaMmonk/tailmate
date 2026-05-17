import { Link } from "react-router-dom";
import { PublicNavbar } from "../components/layout/PublicNavbar";
import { HeroSection } from "../components/landing/HeroSection";
import { FeaturesSection } from "../components/landing/FeaturesSection";
import { HowItWorksSection } from "../components/landing/HowItWorksSection";

export function HomePage() {
  return (
    <main className="pb-16">
      <PublicNavbar />
      <HeroSection />
      <FeaturesSection />
      <HowItWorksSection />
      <footer className="organic-container mt-10 flex w-[min(1180px,calc(100vw-24px))] flex-wrap items-center justify-between gap-3 border-t border-[rgba(222,216,207,0.72)] px-2 pt-8 text-sm text-[var(--organic-muted-text)]">
        <p>Tailmate web client</p>
        <div className="flex gap-4">
          <Link to="/login">Login</Link>
          <a href="https://github.com/DravaMmonk/tailmate-app" target="_blank" rel="noreferrer">
            Repository
          </a>
        </div>
      </footer>
    </main>
  );
}
