import { useEffect, useState } from "react";
import { Empty, Modal, Button, Card } from "antd";
import { ChevronLeft, ChevronRight } from "lucide-react";
import type { HarvestHistoryItem, HarvestInstance } from "../types";
import styles from "./MagazineStackViewer.module.less";

interface MagazineStackViewerProps {
  open: boolean;
  harvest: HarvestInstance;
  items: HarvestHistoryItem[];
  onClose: () => void;
}

export function MagazineStackViewer({
  open,
  harvest,
  items,
  onClose,
}: MagazineStackViewerProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const current = items[currentIndex];

  useEffect(() => {
    setCurrentIndex(0);
  }, [harvest.id, items.length, open]);

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      width={1100}
      title={`${harvest.name} · History`}
      destroyOnHidden
    >
      <div className={styles.viewerContainer}>
        {current ? (
          <>
            <div className={styles.mainArea}>
              <Button
                icon={<ChevronLeft size={18} />}
                disabled={currentIndex === 0}
                onClick={() => setCurrentIndex((prev) => Math.max(prev - 1, 0))}
              />
              <Card className={styles.contentCard}>
                <h3>{current.title}</h3>
                <p className={styles.date}>{current.date.toLocaleString()}</p>
                <p className={styles.content}>{current.content}</p>
              </Card>
              <Button
                icon={<ChevronRight size={18} />}
                disabled={currentIndex === items.length - 1}
                onClick={() =>
                  setCurrentIndex((prev) =>
                    Math.min(prev + 1, items.length - 1),
                  )
                }
              />
            </div>
            <div className={styles.timeline}>
              {items.map((item, index) => (
                <button
                  key={item.id}
                  className={`${styles.timelineItem} ${
                    index === currentIndex ? styles.active : ""
                  }`}
                  onClick={() => setCurrentIndex(index)}
                >
                  <span>{item.date.toLocaleString()}</span>
                </button>
              ))}
            </div>
          </>
        ) : (
          <Empty description="No generated harvest history yet" />
        )}
      </div>
    </Modal>
  );
}
