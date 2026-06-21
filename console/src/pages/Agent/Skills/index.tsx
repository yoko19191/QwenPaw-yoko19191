import { useState } from "react";
import { useTranslation } from "react-i18next";
import { PlusOutlined } from "@ant-design/icons";
import { Button, Tabs } from "@agentscope-ai/design";
import {
  SkillCard,
  SkillDrawer,
  PoolTransferModal,
  ImportHubModal,
  HeaderActions,
  SkillsToolbar,
  SkillListItem,
} from "./components";
import { PageHeader } from "@/components/PageHeader";
import { useSkillsPage } from "./useSkillsPage";
import styles from "./index.module.less";

function SkillsPage() {
  const { t } = useTranslation();
  const {
    skills,
    archivedSkills,
    skillProposals,
    visibleSkills,
    hasMore,
    sentinelRef,
    poolSkills,
    allTags,
    sortedSkills,
    conflictRenameModal,
    loading,
    uploading,
    importing,
    drawerOpen,
    importModalOpen,
    setImportModalOpen,
    editingSkill,
    form,
    fileInputRef,
    poolModal,
    setPoolModal,
    selectedSkills,
    batchModeEnabled,
    viewMode,
    setViewMode,
    filterOpen,
    setFilterOpen,
    searchQuery,
    setSearchQuery,
    searchTags,
    setSearchTags,
    handleCreate,
    handleEdit,
    handleToggleEnabled,
    handleDelete,
    handleArchive,
    handleTogglePinned,
    handleRestoreArchivedSkill,
    handleApplyProposal,
    handleDeleteProposal,
    handleDrawerClose,
    handleSubmit,
    handleUploadToPool,
    handleDownloadFromPool,
    handleBatchEnable,
    handleBatchDisable,
    handleBatchDelete,
    handleUploadClick,
    handleFileChange,
    handleConfirmImport,
    closeImportModal,
    closePoolModal,
    toggleSelect,
    selectAll,
    clearSelection,
    toggleBatchMode,
    toggleEnabled,
    refreshSkills,
    hardRefresh,
    cancelImport,
  } = useSkillsPage();
  const [activeSection, setActiveSection] = useState("active");

  return (
    <div className={styles.skillsPage}>
      <PageHeader
        items={[{ title: t("nav.agent") }, { title: t("skills.title") }]}
        extra={
          <HeaderActions
            batchModeEnabled={batchModeEnabled}
            selectedSkills={selectedSkills}
            loading={loading}
            uploading={uploading}
            fileInputRef={fileInputRef}
            onSelectAll={selectAll}
            onClearSelection={clearSelection}
            onUploadToPool={handleUploadToPool}
            onBatchEnable={handleBatchEnable}
            onBatchDisable={handleBatchDisable}
            onBatchDelete={handleBatchDelete}
            onToggleBatchMode={toggleBatchMode}
            onHardRefresh={hardRefresh}
            onOpenDownloadPool={() => setPoolModal("download")}
            onOpenUploadPool={() => setPoolModal("upload")}
            onUploadClick={handleUploadClick}
            onImportHub={() => setImportModalOpen(true)}
            onCreate={handleCreate}
            onFileChange={handleFileChange}
          />
        }
      />

      <ImportHubModal
        open={importModalOpen}
        importing={importing}
        onCancel={closeImportModal}
        onConfirm={handleConfirmImport}
        cancelImport={cancelImport}
        hint={t("skillPool.externalHubHint")}
      />

      <Tabs
        className={styles.lifecycleTabs}
        activeKey={activeSection}
        onChange={setActiveSection}
        items={[
          {
            key: "active",
            label: `${t("skills.activeTab")} (${skills.length})`,
          },
          {
            key: "archived",
            label: `${t("skills.archivedTab")} (${archivedSkills.length})`,
          },
          {
            key: "proposals",
            label: `${t("skills.proposalsTab")} (${skillProposals.length})`,
          },
        ]}
      />

      {activeSection === "active" && (
        <>
          {!loading && skills.length > 0 && (
            <SkillsToolbar
              searchQuery={searchQuery}
              onSearchChange={setSearchQuery}
              searchTags={searchTags}
              onTagsChange={setSearchTags}
              allTags={allTags}
              filterOpen={filterOpen}
              onFilterOpenChange={setFilterOpen}
              viewMode={viewMode}
              onViewModeChange={setViewMode}
            />
          )}

          {loading ? (
            <div className={styles.loading}>
              <span className={styles.loadingText}>{t("common.loading")}</span>
            </div>
          ) : skills.length === 0 ? (
            <div className={styles.emptyState}>
              <div className={styles.emptyStateBadge}>
                {t("skills.emptyStateBadge")}
              </div>
              <h2 className={styles.emptyStateTitle}>
                {t("skills.emptyStateTitle")}
              </h2>
              <p className={styles.emptyStateText}>
                {t("skills.emptyStateText")}
              </p>
              <div className={styles.emptyStateActions}>
                <Button
                  type="primary"
                  className={styles.primaryActionButton}
                  onClick={handleCreate}
                  icon={<PlusOutlined />}
                >
                  {t("skills.emptyStateCreate")}
                </Button>
              </div>
            </div>
          ) : sortedSkills.length === 0 ? (
            <div className={styles.noSearchResults}>
              <span className={styles.noSearchResultsIcon}>🔍</span>
              <span className={styles.noSearchResultsText}>
                {t("skills.noSearchResults")}
              </span>
            </div>
          ) : viewMode === "card" ? (
            <div className={styles.skillsGrid}>
              {visibleSkills.map((skill) => (
                <SkillCard
                  key={skill.name}
                  skill={skill}
                  selected={
                    batchModeEnabled
                      ? selectedSkills.has(skill.name)
                      : undefined
                  }
                  onSelect={() => toggleSelect(skill.name)}
                  onClick={() => handleEdit(skill)}
                  onMouseEnter={() => {}}
                  onMouseLeave={() => {}}
                  onToggleEnabled={(e) => handleToggleEnabled(skill, e)}
                  onDelete={(e) => handleDelete(skill, e)}
                  onArchive={(e) => handleArchive(skill, e)}
                  onTogglePinned={(e) => handleTogglePinned(skill, e)}
                />
              ))}
              {hasMore && <div ref={sentinelRef} style={{ height: 1 }} />}
            </div>
          ) : (
            <div className={styles.skillsList}>
              {visibleSkills.map((skill) => (
                <SkillListItem
                  key={skill.name}
                  skill={skill}
                  batchModeEnabled={batchModeEnabled}
                  isSelected={selectedSkills.has(skill.name)}
                  onSelect={() => toggleSelect(skill.name)}
                  onClick={() => handleEdit(skill)}
                  onToggleEnabled={async () => {
                    await toggleEnabled(skill);
                    await refreshSkills();
                  }}
                  onDelete={() => handleDelete(skill)}
                  onArchive={() => handleArchive(skill)}
                  onTogglePinned={() => handleTogglePinned(skill)}
                />
              ))}
              {hasMore && <div ref={sentinelRef} style={{ height: 1 }} />}
            </div>
          )}
        </>
      )}

      {activeSection === "archived" && (
        <div className={styles.lifecycleList}>
          {archivedSkills.length === 0 ? (
            <div className={styles.noSearchResults}>
              <span className={styles.noSearchResultsText}>
                {t("skills.noArchivedSkills")}
              </span>
            </div>
          ) : (
            archivedSkills.map((skill) => (
              <div key={skill.archive_id} className={styles.lifecycleItem}>
                <div className={styles.lifecycleItemMain}>
                  <strong>{skill.name}</strong>
                  <span>
                    {skill.archive_reason || "-"} · {t("skills.usage")}:{" "}
                    {skill.use_count || 0}
                  </span>
                </div>
                <Button
                  onClick={() => handleRestoreArchivedSkill(skill.archive_id)}
                >
                  {t("skills.restore")}
                </Button>
              </div>
            ))
          )}
        </div>
      )}

      {activeSection === "proposals" && (
        <div className={styles.lifecycleList}>
          {skillProposals.length === 0 ? (
            <div className={styles.noSearchResults}>
              <span className={styles.noSearchResultsText}>
                {t("skills.noMergeProposals")}
              </span>
            </div>
          ) : (
            skillProposals.map((proposal) => (
              <div key={proposal.id} className={styles.lifecycleItem}>
                <div className={styles.lifecycleItemMain}>
                  <strong>{proposal.suggested_name || proposal.id}</strong>
                  <span>{proposal.source_skills.join(", ")}</span>
                  <span>{proposal.reason || "-"}</span>
                </div>
                <div className={styles.lifecycleActions}>
                  <Button
                    type="primary"
                    onClick={() => handleApplyProposal(proposal.id)}
                  >
                    {t("skills.applyProposal")}
                  </Button>
                  <Button
                    danger
                    onClick={() => handleDeleteProposal(proposal.id)}
                  >
                    {t("common.delete")}
                  </Button>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      <PoolTransferModal
        mode={poolModal}
        skills={skills}
        poolSkills={poolSkills}
        onCancel={closePoolModal}
        onUpload={handleUploadToPool}
        onDownload={handleDownloadFromPool}
      />

      {conflictRenameModal}

      <SkillDrawer
        open={drawerOpen}
        editingSkill={editingSkill}
        form={form}
        availableTags={allTags}
        onClose={handleDrawerClose}
        onSubmit={handleSubmit}
      />
    </div>
  );
}

export default SkillsPage;
