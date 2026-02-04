  MCP server for Confluence Data Center - create pages, manage restrictions, sync user directories                                                                                                                
                                                                                                                                                                                                                  
  ---                                                                                                                                                                                                                                                                                                                                       
                                                                                                                                                                                                                  
  # mcp-confluence-datacenter                                                                                                                                                                                     
                                                                                                                                                                                                                  
  A Model Context Protocol (MCP) server for Confluence Data Center that enables AI assistants to interact with Confluence through a standardized interface.                                                       
                                                                                                                                                                                                                  
  ## Features                                                                                                                                                                                                     
                                                                                                                                                                                                                  
  - **Page Management** - Create new pages with HTML or plain text content                                                                                                                                        
  - **Page Discovery** - List pages in spaces, retrieve child pages with filtering and pagination                                                                                                                 
  - **Access Control** - Add, view, and remove read/edit restrictions for users and groups                                                                                                                        
  - **User Directory Sync** - Trigger synchronization with external directories (e.g., Active Directory)                                                                                                          
                                                                                                                                                                                                                  
  ## Available Tools                                                                                                                                                                                              
                                                                                                                                                                                                                  
  | Tool | Description |                                                                                                                                                                                          
  |------|-------------|                                                                                                                                                                                          
  | `confluence_create_page` | Create a new page in a Confluence space |                                                                                                                                          
  | `confluence_get_space_pages` | List all pages in a space with optional filtering |                                                                                                                            
  | `confluence_get_child_pages` | Get child pages of a specific parent page |                                                                                                                                    
  | `confluence_add_restrictions` | Add read or edit restrictions to a page |                                                                                                                                     
  | `confluence_get_restrictions` | View current restrictions on a page |                                                                                                                                         
  | `confluence_remove_restrictions` | Remove restrictions from a page |                                                                                                                                          
  | `confluence_sync_user_directory` | Sync user directory with external source |                                                                                                                                 
                                                                                                                                                                                                                  
  ## Compatibility                                                                                                                                                                                                
                                                                                                                                                                                                                  
  - Confluence Data Center (on-premise)                                                                                                                                                                           
  - Tested with Confluence 9.x

  - Based on Python FastMCP


                                       