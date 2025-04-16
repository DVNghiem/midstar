from typing import Any, Callable, Dict, List, Optional
from starlette.types import ASGIApp, Scope, Send, Receive

class HTTP2PushMiddleware:
    """
    HTTP/2 Server Push middleware for ASGI applications.
    This middleware enables HTTP/2 Server Push functionality by injecting Link headers 
    with preload directives into HTTP responses. It helps improve page load performance
    by pushing critical resources to the client before they are explicitly requested.
    Usage:
        app = Starlette()
        app.add_middleware(
            HTTP2PushMiddleware,
            push_resources={
                "/": ["/static/css/main.css", "/static/js/app.js"]
            }
        )
    The middleware will only apply server push for HTTP/2 requests and can be further
    controlled using the condition parameter.
    """
    
    def __init__(
       
        self, 
        app: ASGIApp,
        push_resources: Optional[Dict[str, List[str]]] = None,
        condition: Optional[Callable[[Scope], bool]] = None
    ):
        
        """
        Initialize the HTTP/2 Server Push middleware.

        This middleware allows for HTTP/2 Server Push functionality, sending specified resources to the client before they are requested.

        Parameters
        ----------
        app : ASGIApp
            The ASGI application to wrap.
        push_resources : Dict[str, List[str]], optional
            A dictionary mapping paths to lists of resources that should be pushed when those paths are requested.
            For example: {"/": ["/static/style.css", "/static/script.js"]}
        condition : Callable[[Scope], bool], optional
            A function that takes a scope and returns a boolean indicating whether the middleware should be applied.
            Defaults to only applying the middleware for HTTP requests (i.e., when scope["type"] == "http").
        """
        self.app = app
        self.push_resources = push_resources or {}
        self.condition = condition or (lambda scope: scope["type"] == "http")
    
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        # check if the request is HTTP/2
        http_version = scope.get("http_version", "1.1")
        path = scope.get("path", "")

        # check if the request is HTTP/2 and if the path is in push_resources
        if http_version >= "2" and path in self.push_resources and self.condition(scope):
            resources_to_push = self.push_resources[path]
            
            async def wrapped_send(message: Dict[str, Any]) -> None:
                if message["type"] == "http.response.start":
                    # Thêm Link header cho HTTP/2 push
                    headers = message.get("headers", [])
                    
                    # Create Link header 
                    # Link: </styles.css>; rel=preload; as=style, </script.js>; rel=preload; as=script
                    link_header_parts = []
                    for resource in resources_to_push:
                        resource_type = self._get_resource_type(resource)
                        link_part = f"<{resource}>; rel=preload; as={resource_type}"
                        link_header_parts.append(link_part)
                    
                    if link_header_parts:
                        link_header = ", ".join(link_header_parts)
                        headers.append([b"Link", link_header.encode("utf-8")])
                    
                    message["headers"] = headers
                
                await send(message)
            
            await self.app(scope, receive, wrapped_send)
        else:
            await self.app(scope, receive, send)
    
    def _get_resource_type(self, resource: str) -> str:
        """
        Determine the resource type based on the file extension.

        This method categorizes resources into different types based on their file extensions.
        It is used to specify the appropriate resource type for HTTP/2 server push.

        Args:
            resource (str): The path or URL of the resource to categorize.

        Returns:
            str: The resource type, one of:
                - "style" for CSS files
                - "script" for JavaScript files
                - "image" for JPG, JPEG, PNG, GIF, WEBP, or SVG files
                - "font" for WOFF, WOFF2, TTF, OTF, or EOT files
                - "document" for HTML files
                - "fetch" for any other file type
        """
        if resource.endswith((".css")):
            return "style"
        elif resource.endswith((".js")):
            return "script"
        elif resource.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg")):
            return "image"
        elif resource.endswith((".woff", ".woff2", ".ttf", ".otf", ".eot")):
            return "font"
        elif resource.endswith((".html", ".htm")):
            return "document"
        else:
            return "fetch"

    def add_push_resources(self, path: str, resources: List[str]) -> None:
        """
        Add HTTP/2 push resources for a specific path.
        
        This method associates a list of resource URLs with a specific path. When a client
        requests the specified path, the server will push the associated resources to the client
        using HTTP/2 server push.
        
        Parameters:
            path (str): The URL path that will trigger the push resources
            resources (List[str]): A list of resource URLs to be pushed to the client
            
        Returns:
            None
            
        Note:
            If resources are already defined for the given path, the new resources will be appended
            to the existing list.
        """

        if path in self.push_resources:
            self.push_resources[path].extend(resources)
        else:
            self.push_resources[path] = resources

