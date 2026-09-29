import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { AUTO_DIRECTOR_MOBILE_CLASSES } from "@/mobile/autoDirector";

export default function SettingsMaintenanceSection() {
  return (
    <Card className="min-w-0 overflow-hidden">
      <CardHeader>
        <CardTitle>系统维护</CardTitle>
        <CardDescription className={AUTO_DIRECTOR_MOBILE_CLASSES.wrapText}>
          当前使用网页端。更新与数据维护由部署环境统一处理。
        </CardDescription>
      </CardHeader>
      <CardContent className={`text-sm text-muted-foreground ${AUTO_DIRECTOR_MOBILE_CLASSES.wrapText}`}>
        需要备份或迁移数据时，请保留服务端数据目录中的数据库文件与导出文件。
      </CardContent>
    </Card>
  );
}
