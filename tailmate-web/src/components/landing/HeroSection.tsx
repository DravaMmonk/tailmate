import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "../ui/Button";

export function HeroSection() {
  return (
    <section className="relative overflow-hidden px-4 pb-32 pt-16 md:px-6 md:pb-40 md:pt-24">
      <div className="flex flex-col items-center justify-center text-center">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          className="relative z-10 w-full max-w-4xl"
        >
          <h1 className="font-heading text-[clamp(3.2rem,8vw,5.2rem)] leading-[1.1] font-bold tracking-tight text-[var(--organic-foreground)]">
            Understand{" "}
            <span className="italic font-light text-[#C18C5D]">every</span>{" "}
            step.
          </h1>

          <p className="mt-8 text-lg leading-8 text-[#666666]">
            Turn a short video walk into clear, clinical insights about your
            <br />
            dog&apos;s mobility and joint health.
          </p>

          <div className="mt-12 flex flex-wrap items-center justify-center gap-3">
            <Link to="/chat">
              <Button className="px-6">
                Ask Tailmate
                <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
          </div>

          <p className="mt-12 text-sm text-[#888888]">
            Built for consistent home recording and clinically readable trends.
          </p>
        </motion.div>
      </div>
    </section>
  );
}
