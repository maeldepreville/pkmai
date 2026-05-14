import { Modal, App, PluginSettingTab, Setting, Notice, normalizePath } from 'obsidian';
import PkmAiPlugin from './main';
import * as path from 'path';
import * as fs from 'fs';


declare global {
    interface Window {
        electron?: {
            remote?: {
                shell?: {
                    openPath: (path: string) => Promise<string>;
                };
            };
        };
    }
}


class ConfirmDangerModal extends Modal {
    private readonly title: string;
    private readonly message: string;
    private readonly confirmText: string;
    private readonly onConfirm: () => Promise<void>;

    constructor(
        app: App,
        title: string,
        message: string,
        confirmText: string,
        onConfirm: () => Promise<void>,
    ) {
        super(app);
        this.title = title;
        this.message = message;
        this.confirmText = confirmText;
        this.onConfirm = onConfirm;
    }

    onOpen() {
        const { contentEl } = this;

        contentEl.empty();

        contentEl.createEl('h2', { text: this.title });

        contentEl.createEl('p', {
            text: this.message,
        });

        contentEl.createEl('p', {
            text: 'This action cannot be automatically reversed.',
            cls: 'pkmai-danger-text',
        });

        new Setting(contentEl)
            .addButton((button) => {
                button
                    .setButtonText('Cancel')
                    .onClick(() => {
                        this.close();
                    });
            })
            .addButton((button) => {
                button
                    .setButtonText(this.confirmText)
                    .setWarning()
                    .onClick(async () => {
                        this.close();
                        await this.onConfirm();
                    });
            });
    }

    onClose() {
        this.contentEl.empty();
    }
}


export interface PkmAiSettings {
	vault: {
		path: string;
		notes_root_dir: string;
		ignored_dirs: string; // Stored as comma-separated string for UI
	};
	auto_links: {
		enabled: boolean;
		similarity_threshold: number;
		max_links_per_note: number;
		min_note_chars: number;
		section_title: string;
		allow_rewrite_related_section: boolean;
		insert_only_if_missing: boolean;
		embedding: { model_name: string };
		cache: { db_path: string }
	};
	author_mirror: {
		enabled: boolean;
		output_language: string;
		custom_output_language: string;
		output_dir: string;
		prefix: string;
		section_title: string;
		min_chars: number;
		max_note_chars: number;
		overwrite_existing: boolean;
		model: {
			use_custom_path: boolean;
			custom_path: string;
			repo_id: string;
			filename: string;
			n_ctx: number;
			n_threads: number;
			max_tokens: number;
			temperature: number;
			repeat_penalty: number;
		};
		cache: { db_path: string };
	};
}


export const DEFAULT_SETTINGS: PkmAiSettings = {
	vault: {
		path: '',
		notes_root_dir: '',
		ignored_dirs: '.obsidian,Templates,Archive,logs,data,Auteurs Miroirs'
	},
	auto_links: {
		enabled: true,
		similarity_threshold: 0.55,
		max_links_per_note: 5,
		min_note_chars: 50,
		section_title: 'Related Notes',
		allow_rewrite_related_section: true,
		insert_only_if_missing: true,
		embedding: { model_name: 'BAAI/bge-m3' },
		cache: { db_path: 'data/embeddings_cache.sqlite3' }
	},
	author_mirror: {
		enabled: true,
		output_language: 'english',
		custom_output_language: '',
		output_dir: 'Mirror Authors',
		prefix: '[Mirror-Author]',
		section_title: 'Mirror Author',
		min_chars: 120,
		max_note_chars: 24000,
		overwrite_existing: true,
		model: {
			use_custom_path: false,
            custom_path: '',
			repo_id: 'Jackrong/Qwen3.5-2B-Claude-4.6-Opus-Reasoning-Distilled-GGUF',
			filename: 'Qwen3.5-2B.Q8_0.gguf',
			n_ctx: 4096,
			n_threads: 4,
			max_tokens: 1024,
			temperature: 0.3,
			repeat_penalty: 1.15
		},
		cache: { db_path: 'data/author_mirror_cache.sqlite3' }
	}
};


export class PkmAiSettingTab extends PluginSettingTab {
	plugin: PkmAiPlugin;

	constructor(app: App, plugin: PkmAiPlugin) {
		super(app, plugin);
		this.plugin = plugin;
	}

	private getPluginAssetUrl(assetRelativePath: string): string {
		const vaultRelativePath = normalizePath(
			`${this.app.vault.configDir}/plugins/${this.plugin.manifest.id}/${assetRelativePath}`
		);

		return this.app.vault.adapter.getResourcePath(vaultRelativePath);
	}

	private createInfoPanel(
		containerEl: HTMLElement,
		title: string,
		description: string,
		bullets: string[],
	): void {
		const details = containerEl.createEl('details', {
			cls: 'pkmai-settings-info-panel',
		});

		details.createEl('summary', {
			text: title,
		});

		details.createEl('p', {
			text: description,
			cls: 'pkmai-settings-info-description',
		});

		const list = details.createEl('ul', {
			cls: 'pkmai-settings-info-list',
		});

		for (const bullet of bullets) {
			list.createEl('li', { text: bullet });
		}
	}

	display(): void {
		const { containerEl } = this;
		containerEl.empty();

		containerEl.addClass('pkmai-settings-container');

		const header = containerEl.createDiv({ cls: 'pkmai-settings-header' });
		header.style.setProperty(
			'--pkmai-header-bg',
			`url("${this.getPluginAssetUrl('assets/header-bg.png')}")`
		);
		header.createEl('img', {
			cls: 'pkmai-settings-logo',
			attr: {
				src: this.getPluginAssetUrl('assets/logo.png'),
				alt: 'PKM AI logo',
			},
		});
		header.createEl('h1', { text: 'PKM AI' });
		header.createEl('p', {
			text: 'Local, private AI orchestration for your vault.',
			cls: 'pkmai-settings-subtitle',
		});

		containerEl.createEl('h2', { text: '📁 Vault Settings' });

		new Setting(containerEl)
			.setClass('pkmai-setting-card')
			.setName('Detected Vault Path')
			.setDesc('Automatically detected from the currently opened Obsidian vault.')
			.addText((text) => {
				text
					.setValue(this.plugin.getCurrentVaultPath() ?? 'Unavailable')
					.setDisabled(true);
			});

		new Setting(containerEl)
			.setClass('pkmai-setting-card')
			.setName('Notes Root Directory')
			.setDesc('Optional. Leave empty to process the whole vault, or set a subfolder such as "Notes".')
			.addText(text => text
				.setPlaceholder('Notes')
				.setValue(this.plugin.settings.vault.notes_root_dir)
				.onChange(async (value) => {
					this.plugin.settings.vault.notes_root_dir = value.trim();
					await this.plugin.saveSettings();
				})
			);

		new Setting(containerEl)
			.setClass('pkmai-setting-card')
			.setName('Ignored Directories')
			.setDesc('Comma-separated list of folders to skip.')
			.addText(text => text
				.setValue(this.plugin.settings.vault.ignored_dirs)
				.onChange(async (value) => {
					this.plugin.settings.vault.ignored_dirs = value;
					await this.plugin.saveSettings();
				})
			);


		containerEl.createEl('h2', { text: '🕸️ Auto-Links Configuration' });

		this.createInfoPanel(
			containerEl,
			'What does Auto-Links do?',
			'Auto-Links analyzes your markdown notes and inserts a generated section containing semantically related notes.',
			[
				'Scans markdown files in the configured notes root directory.',
				'Ignores folders listed in the ignored directories setting.',
				'Cleans note text before embedding to avoid linking based on generated sections.',
				'Computes local embeddings with the configured SentenceTransformers model.',
				'Uses a SQLite cache so unchanged notes are not embedded again.',
				'Adds a related-notes section to each note when similar notes pass the similarity threshold.',
				'Can be undone from the cleanup button below.',
			],
		);

		new Setting(containerEl)
			.setClass('pkmai-setting-card')
			.setName('Enable Auto-Links')
			.addToggle(toggle => toggle
				.setValue(this.plugin.settings.auto_links.enabled)
				.onChange(async (value) => {
					this.plugin.settings.auto_links.enabled = value;
					await this.plugin.saveSettings();
				})
			);

		new Setting(containerEl)
			.setClass('pkmai-setting-card')
			.setName('Similarity Threshold')
			.setDesc('Higher means stricter matching (0.0 to 1.0).')
			.addSlider(slider => slider
				.setLimits(0.1, 1.0, 0.05)
				.setValue(this.plugin.settings.auto_links.similarity_threshold)
				.setDynamicTooltip()
				.onChange(async (value) => {
					this.plugin.settings.auto_links.similarity_threshold = value;
					await this.plugin.saveSettings();
				})
			);

		new Setting(containerEl)
			.setClass('pkmai-setting-card')
			.setName('Max Links Per Note')
			.addText(text => text
				.setValue(String(this.plugin.settings.auto_links.max_links_per_note))
				.onChange(async (value) => {
					const num = parseInt(value);
					if (!isNaN(num)) {
						this.plugin.settings.auto_links.max_links_per_note = num;
						await this.plugin.saveSettings();
					}
				})
			);

		new Setting(containerEl)
			.setClass('pkmai-setting-card')
			.setName('Min Characters Per Note')
			.addText(text => text
				.setValue(String(this.plugin.settings.auto_links.min_note_chars))
				.onChange(async (value) => {
					const num = parseInt(value);
					if (!isNaN(num)) {
						this.plugin.settings.auto_links.min_note_chars = num;
						await this.plugin.saveSettings();
					}
				})
			);

		new Setting(containerEl)
			.setClass('pkmai-setting-card')
			.setName('Section Title')
			.setDesc('Section Title for Related Notes.')
			.addText(text => text
				.setValue(this.plugin.settings.auto_links.section_title)
				.onChange(async (value) => {
					this.plugin.settings.auto_links.section_title = value;
					await this.plugin.saveSettings();
				})
			);
		
		new Setting(containerEl)
			.setClass('pkmai-setting-card')
			.setName('Allow Rewritting Related Sections')
			.addToggle(toggle => toggle
				.setValue(this.plugin.settings.auto_links.allow_rewrite_related_section)
				.onChange(async (value) => {
					this.plugin.settings.auto_links.allow_rewrite_related_section = value;
					await this.plugin.saveSettings();
				})
			);

		new Setting(containerEl)
			.setClass('pkmai-setting-card')
			.setName('Insert only if Section is Missing')
			.addToggle(toggle => toggle
				.setValue(this.plugin.settings.auto_links.insert_only_if_missing)
				.onChange(async (value) => {
					this.plugin.settings.auto_links.insert_only_if_missing = value;
					await this.plugin.saveSettings();
				})
			);

		new Setting(containerEl)
			.setClass('pkmai-setting-card')
			.setName('Model Name')
			.setDesc('Model Name for embeddings (Hugging Face).')
			.addText(text => text
				.setValue(this.plugin.settings.auto_links.embedding.model_name)
				.onChange(async (value) => {
					this.plugin.settings.auto_links.embedding.model_name = value;
					await this.plugin.saveSettings();
				})
			);

		new Setting(containerEl)
			.setClass('pkmai-setting-card')
			.setName('Cache DB Path')
			.setDesc('Embeddings cache db path.')
			.addText(text => text
				.setValue(this.plugin.settings.auto_links.cache.db_path)
				.onChange(async (value) => {
					this.plugin.settings.auto_links.cache.db_path = value;
					await this.plugin.saveSettings();
				})
			);

		new Setting(containerEl)
			.setName('Undo Auto-Links changes')
			.setDesc(
				'Remove the generated related-notes sections from your notes and clear the Auto-Links embedding cache.',
			)
			.addButton((button) => {
				button
					.setButtonText('Undo Auto-Links')
					.setWarning()
					.onClick(() => {
						new ConfirmDangerModal(
							this.app,
							'Undo Auto-Links changes?',
							'This will remove the generated related-notes section from your markdown notes and delete the Auto-Links cache.',
							'Undo Auto-Links',
							async () => {
								await this.plugin.triggerUndo(
									'/api/v1/links/undo',
									'Auto-Links',
								);
							},
						).open();
					});
			});


		containerEl.createEl('h2', { text: '🧠 Author Mirror Configuration' });

		this.createInfoPanel(
			containerEl,
			'What does Author Mirror do?',
			'Author Mirror reads your notes and generates a dialectical reflection using a local LLM.',
			[
				'Scans eligible markdown notes in the configured notes root directory.',
				'Uses a local llama.cpp-compatible model, either auto-downloaded or manually selected.',
				'Generates a supporting perspective and an opposing perspective.',
				'Creates generated mirror notes in the configured output folder.',
				'Can insert or update an Author Mirror section in the source note.',
				'Uses a local SQLite cache to avoid regenerating unchanged outputs.',
				'Can be undone from the cleanup button below.',
			],
		);

		new Setting(containerEl)
			.setClass('pkmai-setting-card')
			.setName('Enable Author Mirror')
			.addToggle(toggle => toggle
				.setValue(this.plugin.settings.author_mirror.enabled)
				.onChange(async (value) => {
					this.plugin.settings.author_mirror.enabled = value;
					await this.plugin.saveSettings();
				})
			);
		
		new Setting(containerEl)
			.setClass('pkmai-setting-card')
			.setName('Output language')
			.setDesc('Choose the language used for generated Author Mirror notes.')
			.addDropdown((dropdown) => {
				dropdown
					.addOption('english', 'English')
					.addOption('french', 'French')
					.addOption('custom', 'Custom language')
					.setValue(this.plugin.settings.author_mirror.output_language)
					.onChange(async (value) => {
						this.plugin.settings.author_mirror.output_language = value;
						await this.plugin.saveSettings();
						this.display();
					});
			});
		
		if (this.plugin.settings.author_mirror.output_language === 'custom') {
			new Setting(containerEl)
				.setClass('pkmai-setting-card')
				.setName('Custom output language')
				.setDesc('Example: Spanish, German, Italian, Portuguese, Japanese...')
				.addText((text) => {
					text
						.setPlaceholder('Custom Language...')
						.setValue(this.plugin.settings.author_mirror.custom_output_language)
						.onChange(async (value) => {
							this.plugin.settings.author_mirror.custom_output_language = value.trim();
							await this.plugin.saveSettings();
						});
				});
		}

		new Setting(containerEl)
			.setClass('pkmai-setting-card')
			.setName('Use Custom Local Model')
			.setDesc('Turn on to provide a path to your own .gguf file. Leave off to automatically use the built-in lightweight Qwen AI.')
			.addToggle(toggle => toggle
				.setValue(this.plugin.settings.author_mirror.model.use_custom_path)
				.onChange(async (value) => {
					this.plugin.settings.author_mirror.model.use_custom_path = value;
					await this.plugin.saveSettings();
					this.display();
				})
			);

		if (this.plugin.settings.author_mirror.model.use_custom_path) {
			new Setting(containerEl)
				.setName('Custom Model Path')
				.setDesc('Absolute path to the .gguf file on your hard drive.')
				.addText(text => text
					.setPlaceholder('/path/to/your/model.gguf')
					.setValue(this.plugin.settings.author_mirror.model.custom_path)
					.onChange(async (value) => {
						this.plugin.settings.author_mirror.model.custom_path = value;
						await this.plugin.saveSettings();
					})
				);
		} else {
			new Setting(containerEl)
				.setName('Built-in Model Active')
				.setDesc(`The server will automatically download and use the efficient Qwen model. No further action required.`);
		}

		new Setting(containerEl)
			.setClass('pkmai-setting-card')
			.setName('Output Directory')
			.setDesc('Directory name to store the generated notes.')
			.addText(text => text
				.setValue(this.plugin.settings.author_mirror.output_dir)
				.onChange(async (value) => {
					this.plugin.settings.author_mirror.output_dir = value;
					await this.plugin.saveSettings();
				})
			);

		new Setting(containerEl)
			.setClass('pkmai-setting-card')
			.setName('Title Prefix')
			.setDesc('Generated notes title prefix.')
			.addText(text => text
				.setValue(this.plugin.settings.author_mirror.prefix)
				.onChange(async (value) => {
					this.plugin.settings.author_mirror.prefix = value;
					await this.plugin.saveSettings();
				})
			);

		new Setting(containerEl)
			.setClass('pkmai-setting-card')
			.setName('Minimum Notes Characters')
			.addText(text => text
				.setValue(String(this.plugin.settings.author_mirror.min_chars))
				.onChange(async (value) => {
					const num = parseInt(value);
					if (!isNaN(num)) {
						this.plugin.settings.author_mirror.min_chars = num;
						await this.plugin.saveSettings();
					}
				})
			);

		new Setting(containerEl)
			.setClass('pkmai-setting-card')
			.setName('Maximum Generated Note Characters')
			.addText(text => text
				.setValue(String(this.plugin.settings.author_mirror.max_note_chars))
				.onChange(async (value) => {
					const num = parseInt(value);
					if (!isNaN(num)) {
						this.plugin.settings.author_mirror.max_note_chars = num;
						await this.plugin.saveSettings();
					}
				})
			);

		new Setting(containerEl)
			.setClass('pkmai-setting-card')
			.setName('Enable Overwritting Existing Notes')
			.addToggle(toggle => toggle
				.setValue(this.plugin.settings.author_mirror.overwrite_existing)
				.onChange(async (value) => {
					this.plugin.settings.author_mirror.overwrite_existing = value;
					await this.plugin.saveSettings();
				})
			);

		new Setting(containerEl)
			.setClass('pkmai-setting-card')
			.setName('Section Title')
			.setDesc('Section Title for Generated Notes.')
			.addText(text => text
				.setValue(this.plugin.settings.author_mirror.section_title)
				.onChange(async (value) => {
					this.plugin.settings.author_mirror.section_title = value;
					await this.plugin.saveSettings();
				})
			);

		new Setting(containerEl)
			.setClass('pkmai-setting-card')
			.setName('Maximum Context Size')
			.addText(text => text
				.setValue(String(this.plugin.settings.author_mirror.model.n_ctx))
				.onChange(async (value) => {
					const num = parseInt(value);
					if (!isNaN(num)) {
						this.plugin.settings.author_mirror.model.n_ctx = num;
						await this.plugin.saveSettings();
					}
				})
			);

		new Setting(containerEl)
			.setClass('pkmai-setting-card')
			.setName('Number of CPU Threads')
			.addText(text => text
				.setValue(String(this.plugin.settings.author_mirror.model.n_threads))
				.onChange(async (value) => {
					const num = parseInt(value);
					if (!isNaN(num)) {
						this.plugin.settings.author_mirror.model.n_threads = num;
						await this.plugin.saveSettings();
					}
				})
			);

		new Setting(containerEl)
			.setClass('pkmai-setting-card')
			.setName('Maximum Number of Generated Tokens')
			.addText(text => text
				.setValue(String(this.plugin.settings.author_mirror.model.max_tokens))
				.onChange(async (value) => {
					const num = parseInt(value);
					if (!isNaN(num)) {
						this.plugin.settings.author_mirror.model.max_tokens = num;
						await this.plugin.saveSettings();
					}
				})
			);

		new Setting(containerEl)
			.setClass('pkmai-setting-card')
			.setName('Model Temperature')
			.setDesc('Creativity of the generated text (0.0 to 1.0).')
			.addSlider(slider => slider
				.setLimits(0.0, 1.0, 0.1)
				.setValue(this.plugin.settings.author_mirror.model.temperature)
				.setDynamicTooltip()
				.onChange(async (value) => {
					this.plugin.settings.author_mirror.model.temperature = value;
					await this.plugin.saveSettings();
				})
			);

		new Setting(containerEl)
			.setClass('pkmai-setting-card')
			.setName('Model Repetition Penalty')
			.setDesc('Repetition penalty of the generated text (1.0 allowing tokens to repeat freely to 1.5 for strong repetition avoidance).')
			.addSlider(slider => slider
				.setLimits(1.0, 1.5, 0.05)
				.setValue(this.plugin.settings.author_mirror.model.repeat_penalty)
				.setDynamicTooltip()
				.onChange(async (value) => {
					this.plugin.settings.author_mirror.model.repeat_penalty = value;
					await this.plugin.saveSettings();
				})
			);
	
		new Setting(containerEl)
			.setClass('pkmai-setting-card')
			.setName('Cache DB Path')
			.setDesc('Notes cache db path.')
			.addText(text => text
				.setValue(this.plugin.settings.author_mirror.cache.db_path)
				.onChange(async (value) => {
					this.plugin.settings.author_mirror.cache.db_path = value;
					await this.plugin.saveSettings();
				})
			);

		new Setting(containerEl)
			.setName('Undo Author Mirror changes')
			.setDesc(
				'Remove generated Author Mirror sections, delete generated mirror notes, and clear the Author Mirror cache.',
			)
			.addButton((button) => {
				button
					.setButtonText('Undo Author Mirror')
					.setWarning()
					.onClick(() => {
						new ConfirmDangerModal(
							this.app,
							'Undo Author Mirror changes?',
							'This will remove generated Author Mirror sections from your source notes, delete generated mirror notes, and clear the Author Mirror cache.',
							'Undo Author Mirror',
							async () => {
								await this.plugin.triggerUndo(
									'/api/v1/mirror/undo',
									'Author Mirror',
								);
							},
						).open();
					});
			});
		

		containerEl.createEl('h2', { text: '📰 Debug Logs' });
		
		new Setting(containerEl)
			.setName('Check Debug Logs')
			.setDesc('Open the folder containing PKM AI backend logs.')
			.addButton((button) =>
				button
					.setButtonText('Open logs folder')
					.onClick(async () => {
						const logsDir = path.join(
							this.plugin.getPluginDir(),
							'logs'
						);

						fs.mkdirSync(logsDir, { recursive: true });

						const shell = window.electron?.remote?.shell;
						if (!shell) {
							new Notice('Opening logs folder is only available in Obsidian desktop.');
							return;
						}

						const errorMessage = await shell.openPath(logsDir);

						if (errorMessage) {
							new Notice(`Could not open logs folder: ${errorMessage}`);
							return;
						}
					})
			);
	}
}