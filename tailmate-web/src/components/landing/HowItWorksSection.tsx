import { motion } from "framer-motion";

const steps = [
  {
    title: "Create your free account",
    detail: "Sign up with your email in seconds. No credit card required — just your dog's name and you are ready to go.",
  },
  {
    title: "Tell Tailmate about your dog",
    detail: "Add your dog's breed, age, and any health notes. Tailmate keeps this on file so every answer is tailored to your specific pup.",
  },
  {
    title: "Ask anything, any time",
    detail: "Type your question in the chat or send a photo. Tailmate responds instantly with clear, practical advice you can act on right away.",
  },
];

export function HowItWorksSection() {
  return (
    <section id="how-it-works" className="px-4 py-16 md:px-6 md:py-24">
      <div className="organic-container grid max-w-[1180px] gap-8 lg:grid-cols-[320px_minmax(0,1fr)]">
        <motion.div
          initial={{ opacity: 0, x: -24 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true, amount: 0.4 }}
          transition={{ duration: 0.55 }}
          className="lg:sticky lg:top-24 lg:self-start"
        >
          <p className="text-xs uppercase tracking-[0.24em] text-[var(--organic-secondary)]">
            How it works
          </p>
          <h2 className="organic-section-title mt-4 text-4xl font-bold md:text-5xl">
            Up and running in three easy steps.
          </h2>
        </motion.div>
        <div className="space-y-4">
          {steps.map((step, index) => (
            <motion.article
              key={step.title}
              initial={{ opacity: 0, y: 26 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.35 }}
              transition={{ duration: 0.55, delay: index * 0.08 }}
              className="organic-panel organic-panel-strong flex gap-4 p-6 md:p-8"
            >
              <div
                className={[
                  "flex h-12 w-12 shrink-0 items-center justify-center text-sm font-bold text-white shadow-[var(--shadow-soft)]",
                  index === 1
                    ? "rounded-[var(--radius-drop-a)] bg-[var(--organic-secondary)]"
                    : index === 2
                      ? "rounded-[var(--radius-drop-b)] bg-[var(--organic-step-green)]"
                      : "rounded-[2rem] bg-[var(--organic-primary)]",
                ].join(" ")}
              >
                0{index + 1}
              </div>
              <div>
                <h3 className="font-heading text-xl font-bold text-[var(--organic-foreground)]">
                  {step.title}
                </h3>
                <p className="mt-3 text-sm leading-7 text-[var(--organic-muted-text)]">
                  {step.detail}
                </p>
              </div>
            </motion.article>
          ))}
        </div>
      </div>
    </section>
  );
}
