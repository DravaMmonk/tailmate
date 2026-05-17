import {
  createContext,
  startTransition,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { User } from "firebase/auth";
import {
  createUserWithEmailAndPassword,
  onAuthStateChanged,
  onIdTokenChanged,
  signInWithEmailAndPassword,
  signOut,
} from "firebase/auth";
import { activateUser, ensureUserRegistered } from "../lib/api";
import { firebaseAuth, isFirebaseConfigured } from "../lib/firebase";
import type { AuthStatus, UserAccount } from "../types";

interface AuthContextValue {
  status: AuthStatus;
  user: User | null;
  token: string | null;
  account: UserAccount | null;
  authEnabled: boolean;
  backendReady: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  getToken: () => Promise<string | null>;
  refreshIdentity: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

async function syncBackendIdentity(currentUser: User): Promise<{
  token: string;
  account: UserAccount;
}> {
  const token = await currentUser.getIdToken();
  await ensureUserRegistered(token);
  const activation = await activateUser(token);
  return {
    token,
    account: activation.user,
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>(
    isFirebaseConfigured ? "loading" : "signed-out",
  );
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [account, setAccount] = useState<UserAccount | null>(null);
  const [backendReady, setBackendReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!firebaseAuth || !isFirebaseConfigured) {
      setStatus("signed-out");
      return undefined;
    }

    const unsubscribe = onAuthStateChanged(firebaseAuth, (nextUser) => {
      if (!nextUser) {
        startTransition(() => {
          setStatus("signed-out");
          setUser(null);
          setToken(null);
          setAccount(null);
          setBackendReady(false);
          setError(null);
        });
        return;
      }

      setStatus("loading");
      void syncBackendIdentity(nextUser)
        .then((result) => {
          startTransition(() => {
            setUser(nextUser);
            setToken(result.token);
            setAccount(result.account);
            setBackendReady(true);
            setStatus("signed-in");
            setError(null);
          });
        })
        .catch((caughtError: unknown) => {
          startTransition(() => {
            setUser(nextUser);
            setToken(null);
            setAccount(null);
            setBackendReady(false);
            setStatus("signed-in");
            setError(
              caughtError instanceof Error
                ? caughtError.message
                : "Failed to synchronise your Tailmate account.",
            );
          });
        });
    });

    return () => {
      unsubscribe();
    };
  }, []);

  useEffect(() => {
    if (!firebaseAuth || !isFirebaseConfigured) {
      return undefined;
    }

    const unsubscribe = onIdTokenChanged(firebaseAuth, (nextUser) => {
      if (!nextUser) {
        startTransition(() => {
          setToken(null);
        });
        return;
      }

      void nextUser
        .getIdToken()
        .then((nextToken) => {
          startTransition(() => {
            setToken(nextToken);
          });
        })
        .catch(() => {
          startTransition(() => {
            setToken(null);
          });
        });
    });

    return () => {
      unsubscribe();
    };
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      token,
      account,
      authEnabled: isFirebaseConfigured,
      backendReady,
      error,
      async login(email: string, password: string) {
        if (!firebaseAuth) {
          throw new Error("Firebase is not configured for this build.");
        }
        setError(null);
        await signInWithEmailAndPassword(firebaseAuth, email, password);
      },
      async register(email: string, password: string) {
        if (!firebaseAuth) {
          throw new Error("Firebase is not configured for this build.");
        }
        setError(null);
        await createUserWithEmailAndPassword(firebaseAuth, email, password);
      },
      async logout() {
        if (!firebaseAuth) {
          return;
        }
        await signOut(firebaseAuth);
      },
      async getToken() {
        if (!user) {
          return null;
        }
        const nextToken = await user.getIdToken();
        startTransition(() => {
          setToken(nextToken);
        });
        return nextToken;
      },
      async refreshIdentity() {
        if (!user) {
          return;
        }
        const refreshed = await syncBackendIdentity(user);
        startTransition(() => {
          setToken(refreshed.token);
          setAccount(refreshed.account);
          setBackendReady(true);
          setError(null);
        });
      },
    }),
    [account, backendReady, error, status, token, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
