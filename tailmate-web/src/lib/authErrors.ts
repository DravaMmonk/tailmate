export type AuthAction = "login" | "register";

export interface AuthErrorResolution {
  code: string | null;
  message: string;
  disableRegistration: boolean;
}

interface FirebaseErrorLike {
  code?: string;
  message?: string;
}

function getFirebaseErrorCode(error: unknown): string | null {
  if (typeof error !== "object" || error === null || !("code" in error)) {
    return null;
  }

  const { code } = error as FirebaseErrorLike;
  return typeof code === "string" ? code : null;
}

export function resolveAuthActionError(
  error: unknown,
  action: AuthAction,
): AuthErrorResolution {
  const code = getFirebaseErrorCode(error);

  switch (code) {
    case "auth/configuration-not-found":
    case "auth/operation-not-allowed":
      return {
        code,
        disableRegistration: action === "register",
        message:
          action === "register"
            ? "Self-service registration is not available for this deployment. Enable Email/Password sign-in in Firebase Authentication, then try again."
            : "Sign-in is not available for this deployment. Confirm Firebase Authentication is configured correctly, then try again.",
      };
    case "auth/email-already-in-use":
      return {
        code,
        disableRegistration: false,
        message: "That email address is already registered. Try signing in instead.",
      };
    case "auth/invalid-email":
      return {
        code,
        disableRegistration: false,
        message: "Enter a valid email address and try again.",
      };
    case "auth/invalid-credential":
    case "auth/invalid-login-credentials":
    case "auth/user-not-found":
    case "auth/wrong-password":
      return {
        code,
        disableRegistration: false,
        message: "The email or password is incorrect.",
      };
    case "auth/weak-password":
      return {
        code,
        disableRegistration: false,
        message: "Choose a stronger password and try again.",
      };
    case "auth/too-many-requests":
      return {
        code,
        disableRegistration: false,
        message: "Too many authentication attempts were made. Wait a moment and try again.",
      };
    default:
      if (error instanceof Error && error.message.trim()) {
        return {
          code,
          disableRegistration: false,
          message: error.message,
        };
      }

      return {
        code,
        disableRegistration: false,
        message:
          action === "register"
            ? "Registration failed. Try again in a moment."
            : "Authentication failed. Try again in a moment.",
      };
  }
}
