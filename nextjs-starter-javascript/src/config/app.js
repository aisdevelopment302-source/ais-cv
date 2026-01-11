import { AuthStrategy } from "@/lib/auth-strategy";
import { LogLevel } from "@/lib/logger";

export const appConfig = {
	name: "Devias Kit Pro",
	description: "",
	direction: "ltr",
	language: "en",
	theme: "light",
	themeColor: "#090a0b",
	primaryColor: "neonBlue",
	logLevel: process.env.NEXT_PUBLIC_LOG_LEVEL || LogLevel.ALL,
	authStrategy: process.env.NEXT_PUBLIC_AUTH_STRATEGY || AuthStrategy.NONE,
};
