import type { Transition } from "motion/react";

export const motionTransition: Transition = {
  duration: 0.2,
  ease: "easeOut",
};

export const messageEntrance = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
};
