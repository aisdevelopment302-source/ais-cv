import { paths } from "@/paths";

export const dashboardConfig = {
	layout: "vertical",
	navColor: "evident",
	navItems: [
		{
			key: "dashboards",
			title: "Dashboards",
			items: [{ key: "overview", title: "Overview", href: paths.dashboard.overview, icon: "house" }],
		},
		{
			key: "misc",
			title: "Misc",
			items: [{ key: "blank", title: "Blank", href: paths.dashboard.blank, icon: "file-dashed" }],
		},
	],
};
