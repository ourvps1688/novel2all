import SettingsMaintenanceSection from "../components/SettingsMaintenanceSection";
import { SettingsShell } from "../components/SettingsShell";

export default function MaintenanceSettingsPage() {
  return (
    <SettingsShell title="数据与备份" description="查看当前环境下需要自己保留的数据文件。">
      <SettingsMaintenanceSection />
    </SettingsShell>
  );
}
