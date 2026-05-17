import { motion } from "framer-motion";
import { Activity, MessageSquareHeart } from "lucide-react";

const features = [
  {
    icon: Activity,
    title: "Remembers your dog",
    description:
      "Tailmate keeps your dog's name, breed, age, and health history on hand so you never have to repeat yourself. Every conversation picks up right where you left off.",
  },
  {
    icon: MessageSquareHeart,
    title: "Answers arrive instantly",
    description:
      "Responses stream in as they are generated, so you get helpful guidance in seconds — not minutes. Perfect for those late-night worried moments.",
  },
];

export function FeaturesSection() {
  return (
    <section id="features" className="px-4 py-16 md:px-6 md:py-24">
      <div className="organic-container max-w-[1180px]">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.4 }}
          transition={{ duration: 0.6 }}
        >
          <p className="text-xs uppercase tracking-[0.24em] text-[var(--organic-secondary)]">
            Features
          </p>
          <h2 className="organic-section-title mt-4 max-w-[14ch] text-4xl font-bold md:text-5xl">
            Everything a dog parent needs.
          </h2>
        </motion.div>
        <div className="mt-10 grid gap-4 md:grid-cols-3">
          {features.map((feature, index) => {
            const Icon = feature.icon;
            return (
              <motion.article
                key={feature.title}
                initial={{ opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, amount: 0.35 }}
                transition={{ duration: 0.55, delay: index * 0.08 }}
                className="organic-panel organic-panel-strong p-6 transition-transform duration-500 hover:-translate-y-2"
              >
                <div className="flex h-12 w-12 items-center justify-center rounded-[40%_60%_50%_40%] bg-[var(--organic-muted)] text-[var(--organic-primary)]">
                  <Icon className="h-5 w-5" />
                </div>
                <h3 className="font-heading mt-6 text-xl font-bold text-[var(--organic-foreground)]">
                  {feature.title}
                </h3>
                <p className="mt-3 text-sm leading-7 text-[var(--organic-muted-text)]">
                  {feature.description}
                </p>
              </motion.article>
            );
          })}
        </div>
      </div>
    </section>
  );
}
