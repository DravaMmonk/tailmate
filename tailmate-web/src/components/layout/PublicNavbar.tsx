import { AnimatePresence, motion } from "framer-motion";
import { Menu, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { buttonClassName } from "../ui/Button";
import { useAuth } from "../../hooks/useAuth";
import { LANDING_SECTIONS } from "../../lib/constants";

const LOGO_BLOB_PATH =
  "M22 3 C29 3, 40 8, 41 18 C42 28, 36 41, 26 42 C16 43, 4 36, 3 26 C2 16, 8 4, 22 3Z";

export function PublicNavbar() {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-4 z-40 px-4 pt-4 md:px-6">
      <div className="organic-container">
        <div className="organic-pill-nav flex items-center justify-between gap-4 px-4 py-3 md:px-6">
          <Link to="/" className="flex items-center gap-3 text-sm font-bold">
            <motion.svg
              width="44"
              height="44"
              viewBox="0 0 44 44"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              className="flex-shrink-0"
              aria-label="Tailmate logo"
            >
              {/* Flowing irregular rounded-triangle background */}
              <motion.path
                d={LOGO_BLOB_PATH}
                fill="#7E925F"
                animate={{
                  scale: [1, 1.04, 0.98, 1],
                  rotate: [0, 2, -2, 0],
                  opacity: [1, 0.94, 1],
                }}
                transition={{ duration: 5, repeat: Infinity, ease: "easeInOut" }}
                style={{ transformOrigin: "22px 22px" }}
              />
              {/* Dog head logo — scaled and centered from original 1324×1324 viewBox */}
              <g transform="translate(22 22) scale(0.0145) translate(-662 -662)">
                <path
                  d="M770.653 875.743C845.109 930.468 998.509 1067.55 1016.46 1178.09"
                  stroke="white"
                  strokeWidth="50"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M689.057 218.529C681.917 329.169 618.51 408.028 600.321 425.024C575.843 451.537 528.823 519.552 505.976 565.236C477.418 622.341 490.167 736.04 512.606 760.004C535.045 783.967 575.332 838.013 715.065 840.562C854.798 843.112 936.966 768.834 953.223 686.584C970.052 601.436 957.813 578.493 916.505 437.77C883.459 325.193 870.098 254.729 861.938 236.374M1323.46 636.107C1243.57 623.87 1059.4 536.48 961.893 284.811C864.386 33.143 708.946 0.817659 644.179 0.817643C576.012 -2.24153 423.768 15.5017 360.123 110.948C280.568 230.256 251.499 236.374 153.074 236.374C54.6491 236.374 -21.337 184.878 6.20156 341.406C33.7401 497.934 153.074 591.749 256.599 598.887C360.123 606.025 421.83 592.769 467.218 517.309M299.437 640.696C340.404 642.395 426.828 641.104 444.779 622.341M475.888 178.76C468.208 178.76 444.779 178.76 444.779 204.763C444.779 228.991 461.608 233.825 475.888 233.825C490.167 233.825 503.426 218.019 503.426 204.763C503.426 191.506 496.286 178.76 475.888 178.76Z"
                  stroke="white"
                  strokeWidth="42"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </g>
            </motion.svg>
            <span className="font-heading text-xl">Tailmate</span>
          </Link>

          <nav className="hidden items-center gap-2 md:flex">
            {LANDING_SECTIONS.map((item) => (
              <a
                key={item.href}
                href={item.href}
                className="rounded-full px-4 py-2 text-sm font-semibold text-[var(--organic-muted-text)] transition hover:bg-white hover:text-[var(--organic-foreground)]"
              >
                {item.label}
              </a>
            ))}
          </nav>

          <div className="hidden md:block">
            <Link to={user ? "/dashboard" : "/login"} className={buttonClassName("primary", "px-6 text-white")}>
              {user ? "Open App" : "Login"}
            </Link>
          </div>

          <button
            type="button"
            className="flex h-11 w-11 items-center justify-center rounded-full border border-[color:var(--organic-border)] bg-white/70 md:hidden"
            onClick={() => setOpen((value) => !value)}
            aria-label="Toggle navigation"
          >
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>

        <AnimatePresence initial={false}>
          {open ? (
            <motion.div
              initial={{ opacity: 0, y: -12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              className="organic-panel organic-panel-soft mt-3 overflow-hidden p-4 md:hidden"
            >
              <div className="flex flex-col gap-2">
                {LANDING_SECTIONS.map((item) => (
                  <a
                    key={item.href}
                    href={item.href}
                    onClick={() => setOpen(false)}
                    className="rounded-[1.2rem] px-4 py-3 text-sm font-semibold text-[var(--organic-foreground)] hover:bg-[var(--organic-muted)]"
                  >
                    {item.label}
                  </a>
                ))}
                <Link
                  to={user ? "/dashboard" : "/login"}
                  onClick={() => setOpen(false)}
                  className="rounded-[1.2rem] bg-[var(--organic-primary)] px-4 py-3 text-center text-sm font-bold text-white"
                >
                  {user ? "Open App" : "Login"}
                </Link>
              </div>
            </motion.div>
          ) : null}
        </AnimatePresence>
      </div>
    </header>
  );
}
