;;; omni-brain.el --- Cliente Emacs para o Cérebro Único (LangGraph + MCP + HITL) -*- lexical-binding: t; -*-

;; Author: Sukata
;; Version: 1.0.0
;; Package-Requires: ((emacs "28.1") (json "1.5") (url "1.0"))
;; Keywords: tools, ai, langgraph, web3, karmahq, sysop

;;; Commentary:
;; Integra o Emacs diretamente à Fronteira Interna (`role = "admin"`) da API Python
;; do Omni Dual-Brain:
;; - `M-x omni-brain-ask`: Envia prompt autenticado para o grafo Admin.
;; - `M-x omni-brain-send-buffer`: Envia o buffer atual + instrução para análise.
;; - `M-x omni-brain-generate-karmahq-report`: Cruza commits do GitHub + casts da Neynar
;;   e abre o JSON validado em um buffer de revisão Human-in-the-Loop.
;; - `M-x omni-brain-approve-hitl`: Aprova a operação pausada no nó HITL e dispara o POST.

;;; Code:

(require 'json)
(require 'url)

(defgroup omni-brain nil
  "Cliente Emacs para o Cérebro Único com Duas Fronteiras."
  :group 'tools)

(defcustom omni-brain-api-url "http://127.0.0.1:8000"
  "URL base da API FastAPI do Omni Dual-Brain."
  :type 'string
  :group 'omni-brain)

(defcustom omni-brain-admin-user-id "sukata@emacs"
  "Identificador de administrador enviado pelo Emacs."
  :type 'string
  :group 'omni-brain)

(defcustom omni-brain-hmac-secret "change-me-super-secret-hmac-key-for-emacs-and-internal-api"
  "Chave secreta compartilhada para autenticar a Fronteira Interna (role = admin)."
  :type 'string
  :group 'omni-brain)

(defvar omni-brain--last-thread-id nil
  "Último `thread_id` ativo no Emacs para retomada Human-in-the-Loop.")

(defvar omni-brain--last-approval-id nil
  "Último `approval_id` pendente de aprovação no nó HITL.")

(defun omni-brain--display-response (response-alist)
  "Exibe a resposta do Omni Dual-Brain e destaca payloads Human-in-the-Loop."
  (let* ((thread-id (alist-get 'thread_id response-alist))
         (status (alist-get 'status response-alist))
         (reply-text (alist-get 'reply_text response-alist))
         (pending (alist-get 'pending_approval response-alist))
         (buf (get-buffer-create "*Omni-Brain-Admin*")))
    (setq omni-brain--last-thread-id thread-id)
    (when pending
      (setq omni-brain--last-approval-id (alist-get 'approval_id pending)))
    (with-current-buffer buf
      (read-only-mode -1)
      (erase-buffer)
      (insert (format "# Omni Dual-Brain [Thread: %s | Status: %s]\n\n" thread-id status))
      (insert (or reply-text ""))
      (goto-char (point-min))
      (when (fboundp 'markdown-mode)
        (markdown-mode))
      (read-only-mode 1))
    (pop-to-buffer buf)))

(defun omni-brain--post-json (endpoint payload-plist)
  "Envia um POST JSON síncrono para ENDPOINT com PAYLOAD-PLIST."
  (let* ((url-request-method "POST")
         (url-request-extra-headers '(("Content-Type" . "application/json")))
         (url-request-data (encode-coding-string (json-encode payload-plist) 'utf-8))
         (target-url (concat omni-brain-api-url endpoint))
         (response-buffer (url-retrieve-synchronously target-url t nil 30)))
    (unless response-buffer
      (error "Falha ao conectar na API Omni Dual-Brain em %s" target-url))
    (with-current-buffer response-buffer
      (goto-char (point-min))
      (re-search-forward "^$" nil 'move)
      (let* ((json-object-type 'alist)
             (json-array-type 'list)
             (json-key-type 'symbol)
             (parsed (json-read)))
        (kill-buffer response-buffer)
        parsed))))

;;;###autoload
(defun omni-brain-ask (prompt)
  "Envia PROMPT autenticado do Emacs para a Fronteira Interna do LangGraph."
  (interactive "s[Omni-Brain Admin] Comando: ")
  (let ((resp (omni-brain--post-json
               "/api/v1/emacs/command"
               `((message_id . ,(format "emacs-%d" (float-time)))
                 (user_id . ,omni-brain-admin-user-id)
                 (channel . "emacs")
                 (text . ,prompt)
                 (auth_signature . ,omni-brain-hmac-secret)))))
    (omni-brain--display-response resp)))

;;;###autoload
(defun omni-brain-send-buffer (instruction)
  "Envia o conteúdo do buffer atual junto com INSTRUCTION para o Cérebro Único."
  (interactive "s[Omni-Brain Buffer] Instrução sobre o buffer atual: ")
  (let* ((buf-name (buffer-name))
         (buf-content (buffer-substring-no-properties (point-min) (point-max)))
         (resp (omni-brain--post-json
                "/api/v1/emacs/command"
                `((message_id . ,(format "emacs-buf-%d" (float-time)))
                  (user_id . ,omni-brain-admin-user-id)
                  (channel . "emacs")
                  (text . ,instruction)
                  (auth_signature . ,omni-brain-hmac-secret)
                  (emacs_buffer_name . ,buf-name)
                  (emacs_buffer_content . ,buf-content)))))
    (omni-brain--display-response resp)))

;;;###autoload
(defun omni-brain-generate-karmahq-report ()
  "Cruza commits da semana no GitHub + casts da Neynar e pausa para revisão HITL no Emacs."
  (interactive)
  (omni-brain-ask
   "Analise os commits da semana no GitHub e os casts com mais corações na Neynar, monte o JSON de atualização do KarmaHQ e me mande para revisar antes de enviar."))

;;;###autoload
(defun omni-brain-approve-hitl ()
  "Aprova a pendência Human-in-the-Loop ativa e retoma a execução do LangGraph."
  (interactive)
  (unless (and omni-brain--last-thread-id omni-brain--last-approval-id)
    (user-error "Nenhuma aprovação HITL pendente na sessão atual do Emacs"))
  (let ((resp (omni-brain--post-json
               "/api/v1/hitl/decision"
               `((thread_id . ,omni-brain--last-thread-id)
                 (approval_id . ,omni-brain--last-approval-id)
                 (decision . "approved")
                 (admin_user_id . ,omni-brain-admin-user-id)
                 (channel . "emacs")
                 (auth_signature . ,omni-brain-hmac-secret)))))
    (setq omni-brain--last-approval-id nil)
    (omni-brain--display-response resp)))

;;;###autoload
(defun omni-brain-reject-hitl ()
  "Rejeita a pendência Human-in-the-Loop ativa e aborta a ação."
  (interactive)
  (unless (and omni-brain--last-thread-id omni-brain--last-approval-id)
    (user-error "Nenhuma aprovação HITL pendente na sessão atual do Emacs"))
  (let ((resp (omni-brain--post-json
               "/api/v1/hitl/decision"
               `((thread_id . ,omni-brain--last-thread-id)
                 (approval_id . ,omni-brain--last-approval-id)
                 (decision . "rejected")
                 (admin_user_id . ,omni-brain-admin-user-id)
                 (channel . "emacs")
                 (auth_signature . ,omni-brain-hmac-secret)))))
    (setq omni-brain--last-approval-id nil)
    (omni-brain--display-response resp)))

(provide 'omni-brain)
;;; omni-brain.el ends here
